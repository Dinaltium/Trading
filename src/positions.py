"""
Open-position management: valuing spreads, deciding exits, and closing them.

Until now the agent could only open positions. Nothing ever closed one, which meant two
things: a losing spread rode to expiry no matter how far it went against us, and the
"exit-only" kill-switch state was indistinguishable from a full pause — there was nothing
to exit with. This module is what makes both real.

Every decision here is deterministic. Exits are computed from broker-reported P&L and
strikes parsed off the OCC symbols, never from a model. An LLM has no role in deciding
when to cut a loss, for the same reason it has no role in sizing one.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml

from src.alpaca_cli import _redacted_command, _run, _safe_json, verify_paper_endpoint

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "risk_limits.yaml"
OPTION_MULTIPLIER = 100  # one contract controls 100 shares


@dataclass
class Leg:
    symbol: str
    underlying: str
    expiry: date
    option_type: str          # "C" or "P"
    strike: float
    qty: int                  # signed: negative = short
    cost_basis: float
    market_value: float
    unrealized_pl: float


@dataclass
class Spread:
    """A group of legs sharing one underlying and expiry — how Alpaca reports what we
    submitted as a single MLEG order, since it stores legs individually."""
    underlying: str
    expiry: date
    legs: list[Leg] = field(default_factory=list)

    @property
    def contracts(self) -> int:
        return max(abs(leg.qty) for leg in self.legs) if self.legs else 0

    @property
    def net_cost_basis(self) -> float:
        """Positive = we paid a net debit. Negative = we received a net credit."""
        return sum(leg.cost_basis for leg in self.legs)

    @property
    def net_market_value(self) -> float:
        return sum(leg.market_value for leg in self.legs)

    @property
    def unrealized_pl(self) -> float:
        return sum(leg.unrealized_pl for leg in self.legs)

    @property
    def max_loss(self) -> Optional[float]:
        """Worst case in dollars.

        Debit spread: the most you can lose is what you paid.
        Credit spread: the widest vertical, minus the credit taken in. For an iron condor
        only ONE side can finish in the money, so the exposure is the wider wing, not the
        sum of both — treating it as the sum would overstate risk and make the stop-loss
        fire far too late."""
        if not self.legs:
            return None

        net = self.net_cost_basis
        if net > 0:
            return net  # debit paid

        widths = []
        for opt_type in ("C", "P"):
            strikes = sorted(leg.strike for leg in self.legs if leg.option_type == opt_type)
            if len(strikes) >= 2:
                widths.append(max(strikes) - min(strikes))
        if not widths:
            return None

        credit = abs(net)
        return max(widths) * OPTION_MULTIPLIER * self.contracts - credit

    @property
    def max_profit(self) -> Optional[float]:
        """Best case in dollars, the mirror of max_loss.

        Debit spread: the width between the strikes, less what was paid.
        Credit spread: the credit taken in, which is all a short-premium structure can make.
        """
        if not self.legs:
            return None

        net = self.net_cost_basis
        if net <= 0:
            return abs(net)  # credit received is the whole upside

        widths = []
        for opt_type in ("C", "P"):
            strikes = sorted(leg.strike for leg in self.legs if leg.option_type == opt_type)
            if len(strikes) >= 2:
                widths.append(max(strikes) - min(strikes))
        if not widths:
            return None
        return max(widths) * OPTION_MULTIPLIER * self.contracts - net

    @property
    def gain_fraction(self) -> Optional[float]:
        """How much of the best case has already been captured, 0.0 to 1.0. Negative when
        the position is losing."""
        best = self.max_profit
        if not best or best <= 0:
            return None
        return self.unrealized_pl / best

    @property
    def loss_fraction(self) -> Optional[float]:
        """How much of the worst case has already happened, 0.0 to 1.0. Negative when the
        position is profitable."""
        worst = self.max_loss
        if not worst or worst <= 0:
            return None
        return -self.unrealized_pl / worst

    def key(self) -> str:
        return f"{self.underlying}:{self.expiry.isoformat()}"


@dataclass
class ExitDecision:
    spread: Spread
    should_close: bool
    reason: str


def _parse_occ(symbol: str) -> Optional[tuple[str, date, str, float]]:
    """OCC format: ROOT + YYMMDD + C/P + strike*1000, zero-padded to 8 digits.
    e.g. SPY260904C00778000 -> ("SPY", 2026-09-04, "C", 778.0)"""
    if len(symbol) < 15:
        return None
    try:
        strike = int(symbol[-8:]) / 1000.0
        option_type = symbol[-9]
        expiry = datetime.strptime(symbol[-15:-9], "%y%m%d").date()
        underlying = symbol[:-15]
    except (ValueError, IndexError):
        return None
    if option_type not in ("C", "P") or not underlying:
        return None
    return underlying, expiry, option_type, strike


def _load_exit_config() -> dict:
    try:
        with open(CONFIG_PATH, "r") as f:
            return (yaml.safe_load(f) or {}).get("exits") or {}
    except (OSError, yaml.YAMLError):
        return {}


def fetch_open_spreads() -> tuple[list[Spread], Optional[str]]:
    """Read option positions from the broker and group them into spreads.
    Returns (spreads, error). Non-option positions are ignored."""
    result = _run(["position", "list"])
    if not result.ok:
        return [], result.error

    parsed = _safe_json(result.stdout)
    rows = parsed if isinstance(parsed, list) else (parsed or {}).get("positions") or []
    if not isinstance(rows, list):
        return [], f"unexpected position payload: {str(parsed)[:200]}"

    groups: dict[str, Spread] = {}
    for row in rows:
        symbol = (row or {}).get("symbol") or ""
        occ = _parse_occ(symbol)
        if occ is None:
            continue  # equity or crypto position, not ours to manage here
        underlying, expiry, option_type, strike = occ
        try:
            leg = Leg(
                symbol=symbol,
                underlying=underlying,
                expiry=expiry,
                option_type=option_type,
                strike=strike,
                qty=int(float(row.get("qty"))),
                cost_basis=float(row.get("cost_basis")),
                market_value=float(row.get("market_value")),
                unrealized_pl=float(row.get("unrealized_pl")),
            )
        except (TypeError, ValueError):
            continue
        key = f"{underlying}:{expiry.isoformat()}"
        groups.setdefault(key, Spread(underlying=underlying, expiry=expiry)).legs.append(leg)

    return list(groups.values()), None


def evaluate_exits(spreads: list[Spread], config: Optional[dict] = None) -> list[ExitDecision]:
    """Deterministic stop-loss evaluation. No model is consulted."""
    config = config if config is not None else _load_exit_config()
    stop_at = config.get("stop_loss_pct_of_max_loss")
    take_at = config.get("take_profit_pct_of_max_profit")
    decisions = []

    for spread in spreads:
        # Take-profit is evaluated BEFORE the stop, because a position cannot be both and
        # the profitable branch is the one that was missing. Until now the only way out was
        # a loss: a winner was held until expiry no matter how much of its upside it had
        # already captured, which meant the agent never realised a gain, never freed the
        # name for another trade, and never produced a closed winning trade for the
        # adaptive-restriction streak to count.
        gain = spread.gain_fraction
        if take_at is not None and gain is not None and gain >= take_at:
            decisions.append(ExitDecision(
                spread, True,
                f"take-profit: captured {gain:.0%} of max profit (${spread.unrealized_pl:,.2f} "
                f"of ${spread.max_profit:,.2f}), target {take_at:.0%}",
            ))
            continue

        fraction = spread.loss_fraction
        if stop_at is None:
            decisions.append(ExitDecision(spread, False, "no stop-loss configured"))
        elif fraction is None:
            # Cannot value the worst case, so cannot know whether the stop is breached.
            # Hold rather than close: an unmeasurable position is not automatically a
            # losing one, and closing on ignorance pays the spread for nothing.
            decisions.append(ExitDecision(spread, False, "max loss not determinable from legs; holding"))
        elif fraction >= stop_at:
            decisions.append(ExitDecision(
                spread, True,
                f"stop-loss: down {fraction:.0%} of max loss (${spread.unrealized_pl:,.2f} "
                f"of ${spread.max_loss:,.2f}), limit {stop_at:.0%}",
            ))
        else:
            decisions.append(ExitDecision(
                spread, False,
                f"holding: {fraction:.0%} of max loss used, limit {stop_at:.0%}",
            ))
    return decisions


def build_close_args(spread: Spread, client_order_id: str, dry_run: bool = False) -> list[str]:
    """Closing MLEG order: every leg reversed, with explicit close intents.

    Position intents matter here — 'sell_to_close' on a long leg tells Alpaca to reduce an
    existing position rather than open a new short one. Without them a closing order can be
    booked as an opening trade and double the exposure it was meant to remove."""
    legs = []
    for leg in spread.legs:
        is_long = leg.qty > 0
        legs.append({
            "symbol": leg.symbol,
            "ratio_qty": str(abs(leg.qty) // spread.contracts or 1),
            "side": "sell" if is_long else "buy",
            "position_intent": "sell_to_close" if is_long else "buy_to_close",
        })

    # Closing cost is the current mark, sign-flipped: a position worth -142 costs 142 to buy
    # back. Alpaca wants the magnitude; the leg sides carry the direction.
    net_close = -spread.net_market_value / (OPTION_MULTIPLIER * max(spread.contracts, 1))

    import json as _json
    args = [
        "order", "submit",
        "--order-class", "mleg",
        "--qty", str(spread.contracts),
        "--type", "limit",
        "--limit-price", f"{abs(round(net_close, 2)):.2f}",
        "--time-in-force", "day",
        "--legs", _json.dumps(legs, separators=(",", ":")),
        "--client-order-id", client_order_id,
    ]
    if dry_run:
        args.append("--dry-run")
    return args


def close_spread_via_cli(spread: Spread, reason: str, dry_run: bool = False) -> dict:
    """Submit the closing order. Re-verifies the paper endpoint first, exactly as opening
    does — a close is still an order, and the guarantee has to hold on both sides."""
    import uuid

    endpoint = verify_paper_endpoint()
    client_order_id = f"oaa-exit-{uuid.uuid4()}"
    args = build_close_args(spread, client_order_id, dry_run=dry_run)

    result = _run(args)
    record = {
        "action": "close",
        "spread": spread.key(),
        "contracts": spread.contracts,
        "reason": reason,
        "unrealized_pl": spread.unrealized_pl,
        "max_loss": spread.max_loss,
        "endpoint": endpoint,
        "client_order_id": client_order_id,
        "command": _redacted_command(args),
        "dry_run": dry_run,
        "submitted": result.ok and not dry_run,
    }
    if not result.ok:
        record["error"] = result.error
        record["recover_with"] = f"alpaca order get-by-client-id --client-order-id {client_order_id}"
        return record

    response = _safe_json(result.stdout)
    record["response"] = response
    if isinstance(response, dict):
        record["order_id"] = response.get("id")
        record["status"] = response.get("status")
    return record


def manage_open_positions(dry_run: bool = True) -> dict:
    """One exit pass. Safe to call in any trading mode including exit_only — it never opens
    anything. Returns an audit-ready record."""
    spreads, error = fetch_open_spreads()
    if error:
        return {"ok": False, "error": error, "closed": [], "held": []}

    decisions = evaluate_exits(spreads)
    closed, held = [], []
    for decision in decisions:
        if decision.should_close:
            closed.append(close_spread_via_cli(decision.spread, decision.reason, dry_run=dry_run))
        else:
            held.append({
                "spread": decision.spread.key(),
                "unrealized_pl": decision.spread.unrealized_pl,
                "max_loss": decision.spread.max_loss,
                "loss_fraction": decision.spread.loss_fraction,
                "reason": decision.reason,
            })
    return {"ok": True, "open_spreads": len(spreads), "closed": closed, "held": held}


if __name__ == "__main__":
    import json

    spreads, err = fetch_open_spreads()
    if err:
        print(f"error: {err}")
        raise SystemExit(1)
    for s in spreads:
        print(f"{s.key()}  contracts={s.contracts}  net_basis={s.net_cost_basis:+,.2f}  "
              f"unrealized={s.unrealized_pl:+,.2f}  max_loss={s.max_loss}  "
              f"loss_fraction={s.loss_fraction}")
    print()
    print(json.dumps(manage_open_positions(dry_run=True), indent=2, default=str))
