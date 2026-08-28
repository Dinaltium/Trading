"""
Deterministic risk gate. No LLM calls anywhere in this module — every check here
must be independently verifiable by a judge reading the code, not trusted on faith.
See AGENTS.md section 6 and 6b, BRAINSTORM.md section 5 (research pipeline) for rationale.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "risk_limits.yaml"


@dataclass
class TradeProposal:
    strategy: str                    # bull_call_spread | bear_put_spread | iron_condor
    underlying: str                  # e.g. "SPY"
    max_profit_per_contract: float   # dollars, per 1 contract (already x100 multiplier applied)
    max_loss_per_contract: float     # dollars, per 1 contract
    model_confidence: float          # P(win) in [0,1], from the LLM/classifier proposal


@dataclass
class AccountState:
    equity: float
    open_risk_dollars: float         # sum of max_loss across all currently open positions
    open_underlyings: set[str]       # distinct underlyings with an open position right now
    daily_pnl_pct: float             # today's P&L as a fraction of equity, negative = loss


@dataclass
class GateResult:
    approved: bool
    reason: str
    contracts: int = 0


def load_limits(config_path: Path = CONFIG_PATH) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _kelly_fraction(p_win: float, max_profit: float, max_loss: float) -> float:
    """Standard Kelly criterion f* = (p*b - q) / b, b = payoff ratio. Returns 0 if negative edge."""
    if max_loss <= 0:
        return 0.0
    b = max_profit / max_loss
    q = 1.0 - p_win
    f_star = (p_win * b - q) / b
    return max(0.0, f_star)


def evaluate(proposal: TradeProposal, account: AccountState, limits: Optional[dict] = None) -> GateResult:
    limits = limits or load_limits()

    if proposal.strategy not in limits["allowed_strategies"]:
        return GateResult(False, f"strategy '{proposal.strategy}' not in allowed_strategies")

    if account.daily_pnl_pct <= -limits["daily_drawdown_halt_pct"]:
        return GateResult(False, f"daily drawdown halt triggered ({account.daily_pnl_pct:.2%})")

    already_in_this_name = proposal.underlying in account.open_underlyings
    if not already_in_this_name and len(account.open_underlyings) >= limits["max_underlyings_concurrent"]:
        return GateResult(False, f"max_underlyings_concurrent ({limits['max_underlyings_concurrent']}) reached")

    kelly = _kelly_fraction(proposal.model_confidence, proposal.max_profit_per_contract, proposal.max_loss_per_contract)
    if kelly <= 0:
        return GateResult(False, "negative or zero edge per Kelly criterion — no trade")

    sized_fraction = kelly * limits["kelly_fraction"]
    sized_fraction = min(sized_fraction, limits["kelly_cap_pct"], limits["max_loss_per_trade_pct"])

    risk_budget_dollars = account.equity * sized_fraction
    contracts = int(risk_budget_dollars // proposal.max_loss_per_contract)

    if contracts < 1:
        return GateResult(False, "sized position rounds to 0 contracts under risk caps")

    trade_risk_dollars = contracts * proposal.max_loss_per_contract
    projected_open_risk = account.open_risk_dollars + trade_risk_dollars
    max_total_open_risk_dollars = account.equity * limits["max_total_open_risk_pct"]

    if projected_open_risk > max_total_open_risk_dollars:
        # shrink to whatever still fits under the total-open-risk cap, if anything does
        remaining_budget = max_total_open_risk_dollars - account.open_risk_dollars
        contracts = int(remaining_budget // proposal.max_loss_per_contract)
        if contracts < 1:
            return GateResult(False, "max_total_open_risk_pct cap leaves no room for this trade")
        trade_risk_dollars = contracts * proposal.max_loss_per_contract

    return GateResult(
        True,
        f"approved: {contracts} contract(s), risking ${trade_risk_dollars:,.2f} "
        f"({trade_risk_dollars/account.equity:.2%} of equity, Kelly-sized)",
        contracts=contracts,
    )


if __name__ == "__main__":
    # Quick self-check scenarios — not a full test suite, just a sanity pass before wiring into the loop.
    limits = load_limits()
    acct = AccountState(equity=100_000, open_risk_dollars=0, open_underlyings=set(), daily_pnl_pct=0.0)

    good = TradeProposal("iron_condor", "SPY", max_profit_per_contract=150, max_loss_per_contract=350, model_confidence=0.78)
    print(evaluate(good, acct, limits))

    bad_strategy = TradeProposal("naked_call", "SPY", 150, 350, 0.62)
    print(evaluate(bad_strategy, acct, limits))

    no_edge = TradeProposal("iron_condor", "SPY", max_profit_per_contract=150, max_loss_per_contract=350, model_confidence=0.45)
    print(evaluate(no_edge, acct, limits))

    drawdown_acct = AccountState(equity=100_000, open_risk_dollars=0, open_underlyings=set(), daily_pnl_pct=-0.06)
    print(evaluate(good, drawdown_acct, limits))

    diversify_acct = AccountState(equity=100_000, open_risk_dollars=0, open_underlyings={"SPY", "QQQ", "AAPL"}, daily_pnl_pct=0.0)
    print(evaluate(TradeProposal("iron_condor", "MSFT", 150, 350, 0.62), diversify_acct, limits))
