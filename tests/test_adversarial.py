"""Property-based and adversarial tests over the deterministic layer.

The example-based tests elsewhere assert that the guards behave correctly on inputs someone
thought of. These assert invariants over inputs nobody thought of, which is the failure mode
that actually bit: iv_rank sat pinned at exactly 100.0 for four days and every hand-written
test passed the whole time, because none of them asked what a rank means when its window is
one afternoon long.

The properties here are deliberately about what the system must REFUSE. A trading agent's
guards are only interesting at their boundaries, and a generator finds boundaries faster
than a person enumerating cases.
"""

import math

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.decision_schema import decision_matches_rulebook, rulebook_strategy
from src.guards import validate_signals
from src.risk_gate import AccountState, TradeProposal, evaluate, load_limits

STRATEGIES = ["bull_call_spread", "bear_put_spread", "iron_condor", "cash"]

iv_ranks = st.one_of(st.none(), st.floats(min_value=0.0, max_value=100.0))
p_ups = st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0))


# --- rulebook ---------------------------------------------------------------------------

@given(iv_rank=iv_ranks, p_up=p_ups, trusted=st.booleans())
def test_rulebook_only_ever_returns_a_known_strategy(iv_rank, p_up, trusted):
    """No input may produce a strategy the execution layer cannot build."""
    strategy, rationale = rulebook_strategy(iv_rank, p_up, trusted)
    assert strategy in STRATEGIES
    assert isinstance(rationale, str) and rationale


@given(iv_rank=iv_ranks, p_up=p_ups, trusted=st.booleans())
def test_rulebook_is_deterministic(iv_rank, p_up, trusted):
    assert rulebook_strategy(iv_rank, p_up, trusted) == rulebook_strategy(iv_rank, p_up, trusted)


@given(iv_rank=iv_ranks, p_up=p_ups, trusted=st.booleans())
def test_the_mandate_always_passes_its_own_check(iv_rank, p_up, trusted):
    """Otherwise the deterministic fallback could emit a strategy the risk gate then
    rejects as off-rulebook - the agent disagreeing with itself."""
    mandated, _ = rulebook_strategy(iv_rank, p_up, trusted)
    permitted, detail = decision_matches_rulebook(mandated, iv_rank, p_up, trusted)
    assert permitted, detail


@given(iv_rank=iv_ranks, p_up=p_ups, trusted=st.booleans())
def test_cash_is_always_permitted(iv_rank, p_up, trusted):
    """Declining is never off-rulebook. The model's discretion is the discretion to
    decline, and a guard that punished it would delete that property."""
    permitted, _ = decision_matches_rulebook("cash", iv_rank, p_up, trusted)
    assert permitted


@given(
    iv_rank=st.floats(min_value=0.0, max_value=100.0),
    p_up=st.floats(min_value=0.0, max_value=1.0),
    trusted=st.booleans(),
    selected=st.sampled_from(STRATEGIES),
)
def test_a_model_can_never_substitute_a_different_trade(iv_rank, p_up, trusted, selected):
    """The core safety claim: a model may decline a mandated trade but may never propose
    one the rules do not mandate."""
    mandated, _ = rulebook_strategy(iv_rank, p_up, trusted)
    permitted, _ = decision_matches_rulebook(selected, iv_rank, p_up, trusted)
    if permitted:
        assert selected in ("cash", mandated)


@given(
    iv_rank=st.floats(min_value=0.0, max_value=100.0),
    p_up=st.floats(min_value=0.0, max_value=1.0),
)
def test_an_untrusted_window_can_never_mandate_selling_premium(iv_rank, p_up):
    """Selling premium is a bet that options are expensive relative to their own history.
    With no usable history there is no such bet, whatever the number happens to read."""
    mandated, _ = rulebook_strategy(iv_rank, p_up, iv_rank_trusted=False)
    assert mandated != "iron_condor"


@given(iv_rank=iv_ranks, trusted=st.booleans())
def test_a_missing_classifier_is_always_a_full_stop(iv_rank, trusted):
    """Direction is the one signal with no fallback. Absent it there is nothing to trade on
    at all, unlike a missing iv_rank which only withdraws the premium branch."""
    assert rulebook_strategy(iv_rank, None, trusted)[0] == "cash"


# --- signal guard -----------------------------------------------------------------------

@given(
    iv_rank=st.floats(allow_nan=True, allow_infinity=True),
    p_up=st.floats(allow_nan=True, allow_infinity=True),
)
def test_signal_guard_never_raises_on_hostile_numbers(iv_rank, p_up):
    """Guard 1 runs before any model is consulted. If it can be crashed by a NaN it is not
    a guard, it is an outage, and the cycle dies before anything gets to reject it."""
    result = validate_signals({"iv_rank": iv_rank, "classifier_p_up": p_up, "vrp": 0.01})
    assert isinstance(result.passed, bool)


@given(iv_rank=st.floats(allow_nan=True, allow_infinity=True))
def test_out_of_range_or_nan_iv_rank_is_rejected(iv_rank):
    assume(math.isnan(iv_rank) or math.isinf(iv_rank) or not (0.0 <= iv_rank <= 100.0))
    result = validate_signals({"iv_rank": iv_rank, "classifier_p_up": 0.5, "vrp": 0.01})
    assert not result.passed


@given(p_up=st.floats(allow_nan=True, allow_infinity=True))
def test_a_probability_outside_zero_to_one_is_rejected(p_up):
    assume(math.isnan(p_up) or math.isinf(p_up) or not (0.0 <= p_up <= 1.0))
    result = validate_signals({"iv_rank": 50.0, "classifier_p_up": p_up, "vrp": 0.01})
    assert not result.passed


# --- risk gate --------------------------------------------------------------------------

def _account(equity=100_000.0, open_risk=0.0, daily_pnl_pct=0.0):
    return AccountState(
        equity=equity,
        open_risk_dollars=open_risk,
        open_underlyings=set(),
        daily_pnl_pct=daily_pnl_pct,
    )


@settings(max_examples=200, deadline=None)
@given(
    max_loss=st.floats(min_value=1.0, max_value=100_000.0),
    max_profit=st.floats(min_value=0.0, max_value=100_000.0),
    win_prob=st.floats(min_value=0.0, max_value=1.0),
    equity=st.floats(min_value=1_000.0, max_value=1_000_000.0),
    open_risk=st.floats(min_value=0.0, max_value=500_000.0),
    daily_pnl_pct=st.floats(min_value=-0.5, max_value=0.5),
    iv_rank=st.floats(min_value=0.0, max_value=100.0),
    p_up=st.floats(min_value=0.0, max_value=1.0),
    strategy=st.sampled_from(["bull_call_spread", "bear_put_spread", "iron_condor"]),
)
def test_an_approved_trade_never_exceeds_the_per_trade_loss_cap(
    max_loss, max_profit, win_prob, equity, open_risk, daily_pnl_pct, iv_rank, p_up, strategy
):
    """The gate's whole purpose in one property: whatever it approves, the risked amount is
    within the configured fraction of equity. Sizing is the step an LLM is never allowed
    near, so it has to hold for every combination rather than the ones we imagined."""
    cap = load_limits()["max_loss_per_trade_pct"]

    proposal = TradeProposal(
        strategy=strategy,
        underlying="SPY",
        max_profit_per_contract=max_profit,
        max_loss_per_contract=max_loss,
        classifier_win_probability=win_prob,
        iv_rank=iv_rank,
        classifier_p_up=p_up,
    )
    result = evaluate(proposal, _account(equity, open_risk, daily_pnl_pct))
    if result.approved:
        assert result.contracts >= 1
        assert result.contracts * max_loss <= equity * cap + 1e-6


@settings(max_examples=200, deadline=None)
@given(
    max_loss=st.floats(min_value=1.0, max_value=10_000.0),
    win_prob=st.floats(min_value=0.0, max_value=1.0),
    equity=st.floats(min_value=1_000.0, max_value=1_000_000.0),
    loss_pct=st.floats(min_value=0.05, max_value=0.95),
)
def test_the_drawdown_halt_cannot_be_traded_through(max_loss, win_prob, equity, loss_pct):
    """Past the daily loss threshold nothing is approved, regardless of how attractive the
    proposal's own numbers look."""
    assume(loss_pct > load_limits()["daily_drawdown_halt_pct"])

    proposal = TradeProposal(
        strategy="bull_call_spread",
        underlying="SPY",
        max_profit_per_contract=10_000.0,
        max_loss_per_contract=max_loss,
        classifier_win_probability=win_prob,
        iv_rank=50.0,
        classifier_p_up=0.99,
    )
    assert not evaluate(proposal, _account(equity, 0.0, -loss_pct)).approved


@settings(max_examples=200, deadline=None)
@given(
    iv_rank=st.floats(min_value=0.0, max_value=100.0),
    p_up=st.floats(min_value=0.0, max_value=1.0),
    trusted=st.booleans(),
)
def test_the_gate_rederives_the_mandate_and_refuses_substitutions(iv_rank, p_up, trusted):
    """The gate must not trust the strategy name it is handed. It re-derives the mandate
    from the raw signals, so a model that returned a different name is rejected here even
    if everything upstream let it through."""
    mandated, _ = rulebook_strategy(iv_rank, p_up, trusted)
    wrong = next(
        s for s in ("iron_condor", "bull_call_spread", "bear_put_spread") if s != mandated
    )

    proposal = TradeProposal(
        strategy=wrong,
        underlying="SPY",
        max_profit_per_contract=500.0,
        max_loss_per_contract=500.0,
        classifier_win_probability=0.6,
        iv_rank=iv_rank,
        classifier_p_up=p_up,
        iv_rank_trusted=trusted,
    )
    result = evaluate(proposal, _account())
    assert not result.approved
    assert "off-rulebook" in result.reason or "halt" in result.reason
