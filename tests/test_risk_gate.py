"""
Risk-gate behaviour, including the two checks added on 2026-08-30: deterministic rulebook
enforcement and the narrowed premium-selling halt.

Replaces test_risk_gate_state_accumulation.py, which defined no test functions and so
contributed nothing to the suite — pytest collected zero tests from it, and run as a
script it failed at import. Its scenarios are preserved below as real tests.
"""

import pytest

from src.risk_gate import AccountState, GateResult, TradeProposal, evaluate, load_limits

# Signals that mandate an iron_condor: elevated IV, no directional edge.
CONDOR_SIGNALS = {"iv_rank": 75.0, "classifier_p_up": 0.50}
# Signals that mandate a bear_put_spread.
BEARISH_SIGNALS = {"iv_rank": 40.0, "classifier_p_up": 0.40}

SPREAD_ECON = {"max_profit_per_contract": 150.0, "max_loss_per_contract": 350.0}


@pytest.fixture
def limits():
    return load_limits()


def flat_account(**overrides) -> AccountState:
    base = {
        "equity": 100_000.0,
        "open_risk_dollars": 0.0,
        "open_underlyings": set(),
        "daily_pnl_pct": 0.0,
    }
    base.update(overrides)
    return AccountState(**base)


def condor(underlying="SPY", **overrides) -> TradeProposal:
    kwargs = {
        "strategy": "iron_condor",
        "underlying": underlying,
        **SPREAD_ECON,
        "classifier_win_probability": 0.78,
        **CONDOR_SIGNALS,
    }
    kwargs.update(overrides)
    return TradeProposal(**kwargs)


# --- rulebook enforcement -----------------------------------------------------

def test_on_rulebook_strategy_is_approved(limits):
    assert evaluate(condor(), flat_account(), limits).approved


def test_off_rulebook_strategy_is_rejected(limits):
    """The core property: a model cannot manufacture a trade the rules do not mandate.
    These signals mandate a bear_put_spread; a condor must not survive the gate."""
    proposal = condor(strategy="iron_condor", **BEARISH_SIGNALS)
    result = evaluate(proposal, flat_account(), limits)
    assert not result.approved
    assert "off-rulebook" in result.reason
    assert "bear_put_spread" in result.reason


def test_missing_signals_fail_closed(limits):
    """No iv_rank / p_up means the rulebook cannot mandate anything, so nothing but cash
    is permitted. A caller that forgets to pass signals gets no trade, not a free pass."""
    proposal = condor(iv_rank=None, classifier_p_up=None)
    result = evaluate(proposal, flat_account(), limits)
    assert not result.approved
    assert "off-rulebook" in result.reason


def test_strategy_outside_allowed_list_is_rejected(limits):
    result = evaluate(condor(strategy="naked_call"), flat_account(), limits)
    assert not result.approved
    assert "allowed_strategies" in result.reason


# --- premium-selling halt -----------------------------------------------------

def test_premium_selling_halted_at_extreme_iv(limits):
    proposal = condor(iv_rank=95.0, classifier_p_up=0.50)
    result = evaluate(proposal, flat_account(), limits)
    assert not result.approved
    assert "premium-selling halt" in result.reason


def test_condor_allowed_below_halt_threshold(limits):
    """The halt is deliberately narrow. Elevated IV is when a condor is worth selling;
    only the extreme tercile is off-limits. The old blanket veto refused 47 of 47."""
    assert evaluate(condor(iv_rank=89.9, classifier_p_up=0.50), flat_account(), limits).approved


def test_halt_does_not_touch_debit_spreads(limits):
    """Debit spreads are long premium, so the short-vol finding behind the halt does not
    apply to them. Extreme IV with a directional signal must still be tradable."""
    proposal = condor(strategy="bear_put_spread", iv_rank=97.0, classifier_p_up=0.40)
    assert evaluate(proposal, flat_account(), limits).approved


# --- diversification, preserved from the original scenarios -------------------

def test_third_concurrent_underlying_allowed(limits):
    account = flat_account(open_underlyings={"SPY", "QQQ"})
    assert evaluate(condor("AAPL"), account, limits).approved


def test_fourth_concurrent_underlying_rejected(limits):
    account = flat_account(open_underlyings={"SPY", "QQQ", "AAPL"})
    result = evaluate(condor("MSFT"), account, limits)
    assert not result.approved
    assert "max_underlyings_concurrent" in result.reason


def test_re_entry_into_a_held_name_is_refused(limits):
    """Reversed from the original assertion, deliberately.

    This test used to assert that re-entering a name already held was allowed, on the
    reasoning that max_underlyings_concurrent counts distinct names and re-entry is not a
    new name. That is true and was the bug: on the first live session the rulebook mandated
    the same SPY spread three cycles running, the gate approved all three, and the account
    held 28 contracts of one directional bet while every diversification rule reported
    itself satisfied. Three copies of one trade is one bet, not three."""
    account = flat_account(open_underlyings={"SPY", "QQQ", "AAPL"})
    result = evaluate(condor("SPY"), account, limits)
    assert not result.approved
    assert "one position per underlying" in result.reason


def test_a_name_not_yet_held_is_still_allowed(limits):
    """The rule bars re-entry, not entry. Concentration is the target, not activity."""
    account = flat_account(open_underlyings={"SPY", "QQQ"})
    assert evaluate(condor("IWM"), account, limits).approved


# --- drawdown and open-risk caps ---------------------------------------------

@pytest.mark.parametrize(
    "daily_pnl_pct,expected_approved",
    [(0.0, True), (-0.04, True), (-0.05, False), (-0.09, False)],
)
def test_daily_drawdown_halt(limits, daily_pnl_pct, expected_approved):
    account = flat_account(daily_pnl_pct=daily_pnl_pct)
    assert evaluate(condor(), account, limits).approved is expected_approved


def test_open_risk_cap_shrinks_the_position(limits):
    """At the cap boundary the gate reduces size rather than rejecting outright."""
    account = flat_account(open_risk_dollars=9_000.0)  # cap is 10% of 100k
    result = evaluate(condor(), account, limits)
    assert result.approved
    assert result.contracts * SPREAD_ECON["max_loss_per_contract"] <= 1_000.0


def test_open_risk_cap_rejects_when_no_room_remains(limits):
    account = flat_account(open_risk_dollars=9_900.0)
    result = evaluate(condor(), account, limits)
    assert not result.approved
    assert "max_total_open_risk_pct" in result.reason


# --- sizing -------------------------------------------------------------------

def test_negative_edge_is_rejected(limits):
    """Kelly is computed from the calibrated classifier probability, never the model's
    self-reported confidence. A high LLM confidence must not rescue a negative edge."""
    proposal = condor(classifier_win_probability=0.45, llm_confidence_score=0.99)
    result = evaluate(proposal, flat_account(), limits)
    assert not result.approved
    assert "Kelly" in result.reason


def test_sizing_never_exceeds_max_loss_per_trade(limits):
    result: GateResult = evaluate(condor(), flat_account(), limits)
    assert result.approved
    risked = result.contracts * SPREAD_ECON["max_loss_per_contract"]
    assert risked <= 100_000.0 * limits["max_loss_per_trade_pct"]


def test_a_spread_with_no_upside_is_declined_not_crashed(limits):
    """max_profit == 0 makes the Kelly payoff ratio zero and f* = (p*b - q)/b undefined.
    A debit spread quoted at the full width between its strikes has exactly that shape, so
    a wide bid/ask at the open used to raise ZeroDivisionError out of the risk gate and kill
    the cycle - a bad quote taking down the tick instead of being refused by it."""
    from src.risk_gate import AccountState, TradeProposal, evaluate

    proposal = TradeProposal(
        strategy="bear_put_spread",
        underlying="SPY",
        max_profit_per_contract=0.0,
        max_loss_per_contract=400.0,
        classifier_win_probability=0.6,
        iv_rank=50.0,
        classifier_p_up=0.30,
    )
    account = AccountState(
        equity=100_000.0, open_risk_dollars=0.0, open_underlyings=set(), daily_pnl_pct=0.0
    )
    result = evaluate(proposal, account)  # must not raise
    assert not result.approved
