"""
Synthetic multi-cycle test for risk_gate.py's state-dependent checks: diversification
cap, total-open-risk shrink-to-fit, and daily drawdown halt. Deliberately decoupled from
live market data — these paths only fire under specific accumulated account states that
today's real (mostly-cash) signals won't naturally reach before Monday. See BRAINSTORM.md
weekend soak-test section.

Not a pytest suite — plain sequential scenario script, run directly.
"""

from src.risk_gate import AccountState, TradeProposal, evaluate, load_limits

limits = load_limits()


def scenario(name, proposal, account, expect_approved):
    result = evaluate(proposal, account, limits)
    status = "PASS" if result.approved == expect_approved else "FAIL"
    print(f"[{status}] {name}: approved={result.approved} -> {result.reason}")
    return result


spread_econ = dict(max_profit_per_contract=150, max_loss_per_contract=350)

print("--- diversification cap accumulation ---")
state = AccountState(equity=100_000, open_risk_dollars=0, open_underlyings=set(), daily_pnl_pct=0.0)

r1 = scenario("cycle 1: SPY, no positions open yet", TradeProposal("iron_condor", "SPY", **spread_econ, classifier_win_probability=0.78), state, True)
state.open_underlyings.add("SPY")
state.open_risk_dollars += r1.contracts * spread_econ["max_loss_per_contract"]

r2 = scenario("cycle 2: QQQ, SPY already open", TradeProposal("iron_condor", "QQQ", **spread_econ, classifier_win_probability=0.78), state, True)
state.open_underlyings.add("QQQ")
state.open_risk_dollars += r2.contracts * spread_econ["max_loss_per_contract"]

r3 = scenario("cycle 3: AAPL, SPY+QQQ open (3rd is allowed)", TradeProposal("iron_condor", "AAPL", **spread_econ, classifier_win_probability=0.78), state, True)
state.open_underlyings.add("AAPL")
state.open_risk_dollars += r3.contracts * spread_econ["max_loss_per_contract"]

scenario("cycle 4: MSFT, 3 names already open -> should REJECT (cap=3)", TradeProposal("iron_condor", "MSFT", **spread_econ, classifier_win_probability=0.78), state, False)
scenario("cycle 5: SPY again, already open -> should still be ALLOWED (not a new name)", TradeProposal("bull_call_spread", "SPY", **spread_econ, classifier_win_probability=0.78), state, True)

print(f"\naccumulated open_risk_dollars after 3 approved trades: ${state.open_risk_dollars:,.2f} (equity=${state.equity:,.0f})")

print("\n--- total-open-risk shrink-to-fit ---")
# $9,800 of $10,000 cap already used -> only $200 headroom, less than one $350 contract.
# Correct behavior is REJECT (not "blindly approve full 5-contract Kelly size").
near_cap_state = AccountState(equity=100_000, open_risk_dollars=9_800, open_underlyings={"SPY"}, daily_pnl_pct=0.0)
scenario(
    "near the 10% open-risk cap, only $200 headroom left (< 1 contract) -> should REJECT, not blindly approve full size",
    TradeProposal("iron_condor", "SPY", **spread_econ, classifier_win_probability=0.78),
    near_cap_state,
    False,
)

# Same cap, but with more headroom ($1,200) — enough for 3 contracts, less than the full
# 5-contract Kelly size. This is the actual "shrink-to-fit" path, not the reject path above.
partial_room_state = AccountState(equity=100_000, open_risk_dollars=8_800, open_underlyings={"SPY"}, daily_pnl_pct=0.0)
shrink_result = scenario(
    "more headroom ($1,200, room for 3 of 5 Kelly-sized contracts) -> should SHRINK to 3, not reject",
    TradeProposal("iron_condor", "SPY", **spread_econ, classifier_win_probability=0.78),
    partial_room_state,
    True,
)
print(f"  -> shrunk to {shrink_result.contracts} contract(s) (full Kelly size was 5)")

print("\n--- daily drawdown halt ---")
for pnl in [-0.01, -0.03, -0.049, -0.05, -0.08]:
    dd_state = AccountState(equity=100_000, open_risk_dollars=0, open_underlyings=set(), daily_pnl_pct=pnl)
    expect = pnl > -limits["daily_drawdown_halt_pct"]
    scenario(f"daily_pnl_pct={pnl:.1%}", TradeProposal("iron_condor", "SPY", **spread_econ, classifier_win_probability=0.78), dd_state, expect)
