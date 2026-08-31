"""
Defined-risk spread construction and ATOMIC multi-leg execution.

This is the item-6 fix from the blueprint: every spread submits as ONE order via
Alpaca's OrderClass.MLEG with a `legs` list, never as a loop of individual leg orders.
A loop-based submission is the bug that can leave a naked, unbalanced position on a
partial fill — the opposite of "defined-risk". See BRAINSTORM.md section 9/10.

Contracts are resolved from the live option chain by delta, never by hand-building an
OCC symbol — per the alpaca-trading-paper-trading-mcp skill's rule 19.
"""

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml
from typing import Optional

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, PositionIntent, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

# Target deltas for strike selection. Short strikes near ~0.20 delta is the common
# "one standard deviation-ish" premium-selling convention; long/protective legs further
# OTM near ~0.10 delta to cap the spread width and hence max loss.
SHORT_LEG_TARGET_DELTA = 0.20
LONG_LEG_TARGET_DELTA = 0.10  # for iron condor's protective wings
DEBIT_SPREAD_LONG_DELTA = 0.40  # bull_call/bear_put's directional leg
DEBIT_SPREAD_SHORT_DELTA = 0.20  # bull_call/bear_put's premium-offsetting leg


@dataclass
class SpreadLeg:
    symbol: str
    side: OrderSide
    position_intent: PositionIntent
    strike: float
    delta: float
    mid_price: float


@dataclass
class SpreadOrder:
    strategy: str
    underlying: str
    legs: list[SpreadLeg]
    max_profit_per_contract: float  # dollars, x100 multiplier applied
    max_loss_per_contract: float
    net_price: float  # positive = net debit (bull_call/bear_put), negative = net credit (iron_condor)


def _parse_occ(symbol: str) -> tuple[str, float]:
    """Returns (option_type, strike) from an OCC-format symbol. Used only to read
    fields off contracts the chain endpoint already gave us — never to hand-build one."""
    opt_type = "call" if symbol[-9] == "C" else "put"
    strike = int(symbol[-8:]) / 1000.0
    return opt_type, strike


def _mid_price(snap) -> Optional[float]:
    if snap.latest_quote and snap.latest_quote.bid_price and snap.latest_quote.ask_price:
        return (snap.latest_quote.bid_price + snap.latest_quote.ask_price) / 2.0
    return None


def _load_execution_config() -> dict:
    """Execution constraints live in risk_limits.yaml alongside the other hard limits,
    hand-edited only — an expiry the agent must not touch is a risk rule, not a preference."""
    try:
        with open(Path(__file__).resolve().parent.parent / "config" / "risk_limits.yaml", "r") as f:
            return (yaml.safe_load(f) or {}).get("execution") or {}
    except (OSError, yaml.YAMLError):
        return {}


def _excluded_expiries() -> set:
    raw = _load_execution_config().get("excluded_expiries") or []
    out = set()
    for item in raw:
        if isinstance(item, date):
            out.add(item)
        else:
            try:
                out.add(datetime.strptime(str(item), "%Y-%m-%d").date())
            except ValueError:
                continue
    return out


def _nearest_expiry_chain(chain: dict, target_dte_days: int = 7) -> dict:
    """Filters the full chain to whichever expiry date is closest to target_dte_days out.
    Defaults to ~weekly, per AGENTS.md's 'favor short-dated options' guidance."""
    from datetime import datetime

    expiries = {}
    for symbol in chain:
        exp_str = symbol[3:9] if symbol[3].isdigit() else symbol[4:10]  # tolerate 1-2 letter roots
        try:
            exp_date = datetime.strptime(exp_str, "%y%m%d")
        except ValueError:
            continue
        expiries.setdefault(exp_date, []).append(symbol)

    # Drop any expiry the risk config forbids before choosing. Filtering after selection
    # would silently fall back to no trade; filtering before picks the next-best expiry.
    for banned in _excluded_expiries():
        expiries.pop(banned, None)

    if not expiries:
        return {}
    today = datetime.now()
    best_exp = min(expiries.keys(), key=lambda d: abs((d - today).days - target_dte_days))
    return {sym: chain[sym] for sym in expiries[best_exp]}


def _select_by_delta(chain: dict, opt_type: str, target_delta: float) -> Optional[tuple[str, object]]:
    """Nearest contract of the given type to target_delta (signed: negative for puts)."""
    signed_target = -target_delta if opt_type == "put" else target_delta
    best_symbol, best_snap, best_diff = None, None, float("inf")
    for symbol, snap in chain.items():
        if snap.greeks is None or snap.greeks.delta is None:
            continue
        this_type, _ = _parse_occ(symbol)
        if this_type != opt_type:
            continue
        diff = abs(snap.greeks.delta - signed_target)
        if diff < best_diff:
            best_diff, best_symbol, best_snap = diff, symbol, snap
    return (best_symbol, best_snap) if best_symbol else None


def build_spread(
    opt_client: OptionHistoricalDataClient,
    underlying: str,
    strategy: str,
    target_dte_days: int = 7,
) -> Optional[SpreadOrder]:
    full_chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=underlying))
    chain = _nearest_expiry_chain(full_chain, target_dte_days)
    if not chain:
        return None

    if strategy == "bull_call_spread":
        long_pick = _select_by_delta(chain, "call", DEBIT_SPREAD_LONG_DELTA)
        short_pick = _select_by_delta(chain, "call", DEBIT_SPREAD_SHORT_DELTA)
        if not long_pick or not short_pick:
            return None
        legs = [
            _to_leg(long_pick, OrderSide.BUY, PositionIntent.BUY_TO_OPEN),
            _to_leg(short_pick, OrderSide.SELL, PositionIntent.SELL_TO_OPEN),
        ]

    elif strategy == "bear_put_spread":
        long_pick = _select_by_delta(chain, "put", DEBIT_SPREAD_LONG_DELTA)
        short_pick = _select_by_delta(chain, "put", DEBIT_SPREAD_SHORT_DELTA)
        if not long_pick or not short_pick:
            return None
        legs = [
            _to_leg(long_pick, OrderSide.BUY, PositionIntent.BUY_TO_OPEN),
            _to_leg(short_pick, OrderSide.SELL, PositionIntent.SELL_TO_OPEN),
        ]

    elif strategy == "iron_condor":
        short_put = _select_by_delta(chain, "put", SHORT_LEG_TARGET_DELTA)
        long_put = _select_by_delta(chain, "put", LONG_LEG_TARGET_DELTA)
        short_call = _select_by_delta(chain, "call", SHORT_LEG_TARGET_DELTA)
        long_call = _select_by_delta(chain, "call", LONG_LEG_TARGET_DELTA)
        if not all([short_put, long_put, short_call, long_call]):
            return None
        legs = [
            _to_leg(short_put, OrderSide.SELL, PositionIntent.SELL_TO_OPEN),
            _to_leg(long_put, OrderSide.BUY, PositionIntent.BUY_TO_OPEN),
            _to_leg(short_call, OrderSide.SELL, PositionIntent.SELL_TO_OPEN),
            _to_leg(long_call, OrderSide.BUY, PositionIntent.BUY_TO_OPEN),
        ]

    else:
        return None

    if any(leg.mid_price is None for leg in legs):
        return None

    net_price = sum(leg.mid_price if leg.side == OrderSide.BUY else -leg.mid_price for leg in legs)
    strikes = sorted({leg.strike for leg in legs})
    width = (strikes[-1] - strikes[0]) if len(strikes) >= 2 else 0.0

    if strategy in ("bull_call_spread", "bear_put_spread"):
        max_loss = net_price * 100.0
        max_profit = (width - net_price) * 100.0
    else:  # iron_condor: net_price is negative (credit received)
        credit = -net_price
        max_profit = credit * 100.0
        # width of whichever wing is wider (put side vs call side) minus credit received
        put_strikes = sorted(leg.strike for leg in legs if _parse_occ(leg.symbol)[0] == "put")
        call_strikes = sorted(leg.strike for leg in legs if _parse_occ(leg.symbol)[0] == "call")
        wing_width = max(put_strikes[-1] - put_strikes[0], call_strikes[-1] - call_strikes[0])
        max_loss = (wing_width - credit) * 100.0

    return SpreadOrder(
        strategy=strategy,
        underlying=underlying,
        legs=legs,
        max_profit_per_contract=round(max_profit, 2),
        max_loss_per_contract=round(max_loss, 2),
        net_price=round(net_price, 4),
    )


def _to_leg(pick: tuple[str, object], side: OrderSide, intent: PositionIntent) -> SpreadLeg:
    symbol, snap = pick
    _, strike = _parse_occ(symbol)
    return SpreadLeg(
        symbol=symbol,
        side=side,
        position_intent=intent,
        strike=strike,
        delta=snap.greeks.delta,
        mid_price=_mid_price(snap),
    )


def submit_spread_order(trading_client: TradingClient, spread: SpreadOrder, contracts: int):
    """Submits every leg as ONE atomic multi-leg order (OrderClass.MLEG). This is the
    item-6 fix — never loop individual leg submissions."""
    order_legs = [
        OptionLegRequest(symbol=leg.symbol, ratio_qty=1, side=leg.side, position_intent=leg.position_intent)
        for leg in spread.legs
    ]
    # net_price sign convention: positive = pay a debit, negative = receive a credit.
    # Alpaca's multi-leg limit_price is the net price for the whole spread, same sign convention.
    # Cross the spread slightly rather than resting exactly at the mid. A mid-priced
    # multi-leg limit often simply does not fill, and an unfilled order is indistinguishable
    # in the P&L from a trade never proposed. The cushion moves the limit in the direction
    # that helps it fill and never the other way: pay above mid on a debit, accept below mid
    # on a credit. See risk_limits.yaml execution.limit_price_cushion.
    cushion = float(_load_execution_config().get("limit_price_cushion", 0.0))
    is_debit = spread.net_price >= 0
    limit_price = abs(spread.net_price) + cushion if is_debit else max(0.01, abs(spread.net_price) - cushion)

    request = LimitOrderRequest(
        qty=contracts,
        side=OrderSide.BUY if is_debit else OrderSide.SELL,
        type="limit",
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.MLEG,
        limit_price=round(limit_price, 2),
        legs=order_legs,
    )
    return trading_client.submit_order(order_data=request)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=True)
    key, sec = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    opt_client = OptionHistoricalDataClient(key, sec)

    for strategy in ["bull_call_spread", "bear_put_spread", "iron_condor"]:
        spread = build_spread(opt_client, "SPY", strategy)
        print(f"--- {strategy} ---")
        if spread is None:
            print("could not build (missing chain data)")
            continue
        for leg in spread.legs:
            print(f"  {leg.side.value:5s} {leg.symbol}  strike={leg.strike}  delta={leg.delta:.3f}  mid={leg.mid_price}")
        print(f"  net_price={spread.net_price}  max_profit/ctr=${spread.max_profit_per_contract}  max_loss/ctr=${spread.max_loss_per_contract}")
