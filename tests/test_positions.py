"""
Spread valuation, stop-loss evaluation, and closing-order construction.

The worked example throughout is the real iron condor that sat on the dev account on
2026-08-30: SPY 260904, short 778C / long 782C / long 752P / short 760P, opened for a $150
net credit.
"""

import json
from datetime import date

import pytest

from src.positions import (
    Leg,
    Spread,
    _parse_occ,
    build_close_args,
    evaluate_exits,
)


def leg(symbol, qty, cost_basis, market_value, unrealized_pl):
    underlying, expiry, opt_type, strike = _parse_occ(symbol)
    return Leg(symbol=symbol, underlying=underlying, expiry=expiry, option_type=opt_type,
               strike=strike, qty=qty, cost_basis=cost_basis, market_value=market_value,
               unrealized_pl=unrealized_pl)


@pytest.fixture
def condor():
    """The real position, exactly as the broker reported it."""
    return Spread(underlying="SPY", expiry=date(2026, 9, 4), legs=[
        leg("SPY260904C00778000", -1, -108.0, -103.0, 5.0),
        leg("SPY260904C00782000", 1, 40.0, 39.0, -1.0),
        leg("SPY260904P00752000", 1, 62.0, 53.0, -9.0),
        leg("SPY260904P00760000", -1, -144.0, -131.0, 13.0),
    ])


@pytest.fixture
def debit_spread():
    return Spread(underlying="SPY", expiry=date(2026, 9, 8), legs=[
        leg("SPY260908P00760000", 1, 300.0, 200.0, -100.0),
        leg("SPY260908P00750000", -1, -100.0, -60.0, 40.0),
    ])


# --- OCC parsing --------------------------------------------------------------

def test_parse_occ_call():
    assert _parse_occ("SPY260904C00778000") == ("SPY", date(2026, 9, 4), "C", 778.0)


def test_parse_occ_put_with_fractional_strike():
    assert _parse_occ("QQQ260904P00612500") == ("QQQ", date(2026, 9, 4), "P", 612.5)


def test_parse_occ_rejects_equity_symbol():
    assert _parse_occ("SPY") is None
    assert _parse_occ("BTC/USD") is None


# --- valuation ----------------------------------------------------------------

def test_condor_net_credit(condor):
    assert condor.net_cost_basis == -150.0  # credit received


def test_condor_max_loss_uses_the_wider_wing_only(condor):
    """Only one side of a condor can finish in the money. Summing both wings would
    overstate risk and make the stop fire far too late."""
    # put wing 760-752 = 8 wide; call wing 782-778 = 4 wide
    assert condor.max_loss == 8 * 100 * 1 - 150  # 650


def test_condor_unrealized_and_loss_fraction(condor):
    assert condor.unrealized_pl == 8.0
    assert condor.loss_fraction == pytest.approx(-8.0 / 650.0)


def test_debit_spread_max_loss_is_the_debit_paid(debit_spread):
    assert debit_spread.net_cost_basis == 200.0
    assert debit_spread.max_loss == 200.0


def test_loss_fraction_is_positive_when_losing(debit_spread):
    assert debit_spread.unrealized_pl == -60.0
    assert debit_spread.loss_fraction == pytest.approx(0.30)


def test_empty_spread_has_no_max_loss():
    assert Spread(underlying="SPY", expiry=date(2026, 9, 4)).max_loss is None


# --- stop-loss ----------------------------------------------------------------

CONFIG = {"stop_loss_pct_of_max_loss": 0.60}


def test_profitable_position_is_held(condor):
    decision = evaluate_exits([condor], CONFIG)[0]
    assert not decision.should_close


def test_position_below_the_stop_is_held(debit_spread):
    """30% of max loss used against a 60% limit."""
    decision = evaluate_exits([debit_spread], CONFIG)[0]
    assert not decision.should_close
    assert "30%" in decision.reason


def test_position_at_the_stop_is_closed():
    spread = Spread(underlying="SPY", expiry=date(2026, 9, 8), legs=[
        leg("SPY260908P00760000", 1, 300.0, 120.0, -180.0),
        leg("SPY260908P00750000", -1, -100.0, -40.0, 60.0),
    ])
    assert spread.loss_fraction == pytest.approx(0.60)
    decision = evaluate_exits([spread], CONFIG)[0]
    assert decision.should_close
    assert "stop-loss" in decision.reason


def test_no_configured_stop_never_closes(condor):
    assert not evaluate_exits([condor], {})[0].should_close


def test_unvaluable_spread_is_held_not_closed():
    """A single orphan leg has no determinable worst case. Closing on ignorance pays the
    bid-ask spread for nothing, so the safe default is to hold and say why."""
    spread = Spread(underlying="SPY", expiry=date(2026, 9, 8), legs=[
        leg("SPY260908P00760000", -1, -100.0, -90.0, 10.0),
    ])
    decision = evaluate_exits([spread], CONFIG)[0]
    assert not decision.should_close
    assert "not determinable" in decision.reason


# --- closing order ------------------------------------------------------------

def test_close_reverses_every_leg_with_close_intents(condor):
    args = build_close_args(condor, "test-id")
    legs = json.loads(args[args.index("--legs") + 1])
    by_symbol = {l["symbol"]: l for l in legs}

    # long legs are sold to close
    assert by_symbol["SPY260904C00782000"]["side"] == "sell"
    assert by_symbol["SPY260904C00782000"]["position_intent"] == "sell_to_close"
    # short legs are bought to close
    assert by_symbol["SPY260904C00778000"]["side"] == "buy"
    assert by_symbol["SPY260904C00778000"]["position_intent"] == "buy_to_close"


def test_close_price_is_the_cost_to_buy_back(condor):
    """Position marked at -142 costs 1.42/contract to close. Alpaca wants the magnitude."""
    args = build_close_args(condor, "test-id")
    assert args[args.index("--limit-price") + 1] == "1.42"


def test_close_is_a_single_mleg_order(condor):
    args = build_close_args(condor, "test-id")
    assert args[args.index("--order-class") + 1] == "mleg"
    assert args[args.index("--qty") + 1] == "1"


def test_dry_run_flag_is_opt_in(condor):
    assert "--dry-run" not in build_close_args(condor, "id")
    assert "--dry-run" in build_close_args(condor, "id", dry_run=True)


# --- underlying root derivation --------------------------------------------------------
# Guard 4 compares the agent's believed position map against an independent read of broker
# state. Both sides must spell the underlying identically or every four-letter ticker
# reconciles as simultaneously missing and phantom, blocking the order.

def test_underlying_root_handles_three_and_four_letter_tickers():
    from src.alpaca_cli import underlying_root

    assert underlying_root("SPY260904P00752000") == "SPY"
    assert underlying_root("QQQ260904C00600000") == "QQQ"
    assert underlying_root("IWM260904P00290000") == "IWM"
    assert underlying_root("AAPL260904C00320000") == "AAPL"


def test_both_sides_of_reconciliation_agree_on_the_root():
    """The orchestrator's believed set and the CLI's broker read must derive roots the same
    way. symbol[:3] was right for SPY by luck and turned AAPL into AAP."""
    from src.alpaca_cli import underlying_root

    for symbol, expected in [
        ("AAPL260904C00320000", "AAPL"),
        ("SPY260904P00752000", "SPY"),
    ]:
        believed = underlying_root(symbol) if len(symbol) > 6 else symbol
        broker = underlying_root(symbol)
        assert believed == broker == expected


# --- take-profit -------------------------------------------------------------------------
# Until this existed the only exit was a loss. A winner was held to expiry no matter how
# much of its upside it had captured, which meant the agent never realised a gain, never
# freed the name for another trade under one_position_per_underlying, and never produced a
# closed winning trade for the adaptive-restriction streak to count.

def _debit_spread(unrealized_pl, paid=200.0, width=4.0):
    """A 1-contract debit spread: paid `paid` dollars, strikes `width` apart."""
    from src.positions import Leg, Spread
    from datetime import date

    return Spread(
        underlying="SPY",
        expiry=date(2026, 9, 8),
        legs=[
            Leg("SPY260908P00764000", "SPY", date(2026, 9, 8), "P", 764.0, 1, paid, paid + unrealized_pl, unrealized_pl),
            Leg("SPY260908P00760000", "SPY", date(2026, 9, 8), "P", 764.0 - width, -1, 0.0, 0.0, 0.0),
        ],
    )


def test_take_profit_closes_a_winner_at_the_target():
    from src.positions import evaluate_exits

    cfg = {"stop_loss_pct_of_max_loss": 0.60, "take_profit_pct_of_max_profit": 0.50}
    spread = _debit_spread(unrealized_pl=120.0, paid=200.0, width=4.0)  # max profit 400-200=200
    decision = evaluate_exits([spread], cfg)[0]
    assert decision.should_close
    assert "take-profit" in decision.reason


def test_a_winner_below_the_target_is_held():
    from src.positions import evaluate_exits

    cfg = {"stop_loss_pct_of_max_loss": 0.60, "take_profit_pct_of_max_profit": 0.50}
    decision = evaluate_exits([_debit_spread(unrealized_pl=40.0)], cfg)[0]
    assert not decision.should_close


def test_take_profit_is_evaluated_before_the_stop():
    """A position cannot be both, and the profitable branch is the one that was missing."""
    from src.positions import evaluate_exits

    cfg = {"stop_loss_pct_of_max_loss": 0.60, "take_profit_pct_of_max_profit": 0.50}
    decision = evaluate_exits([_debit_spread(unrealized_pl=150.0)], cfg)[0]
    assert decision.should_close
    assert "take-profit" in decision.reason


def test_losers_still_stop_out():
    from src.positions import evaluate_exits

    cfg = {"stop_loss_pct_of_max_loss": 0.60, "take_profit_pct_of_max_profit": 0.50}
    decision = evaluate_exits([_debit_spread(unrealized_pl=-150.0)], cfg)[0]
    assert decision.should_close
    assert "stop-loss" in decision.reason


def test_no_take_profit_configured_falls_back_to_stop_only():
    from src.positions import evaluate_exits

    cfg = {"stop_loss_pct_of_max_loss": 0.60}
    assert not evaluate_exits([_debit_spread(unrealized_pl=180.0)], cfg)[0].should_close


# --- flatten -----------------------------------------------------------------------------
# The operator's panic button. exit_only answers "stop taking risk"; flatten answers "get me
# out of the risk I already have", and the second is what someone actually wants when
# something looks wrong.

def test_flatten_closes_positions_the_exit_rules_would_have_held(monkeypatch):
    """The whole point. A flatten filtered through evaluate_exits() would close only what the
    stop-loss already wanted closed, and so do nothing in the situation it exists for."""
    import src.positions as P

    spread = _debit_spread(unrealized_pl=10.0)  # comfortably inside both stop and target
    assert not P.evaluate_exits([spread], {"stop_loss_pct_of_max_loss": 0.60})[0].should_close

    monkeypatch.setattr(P, "fetch_open_spreads", lambda: ([spread], None))
    monkeypatch.setattr(P, "cancel_open_orders", lambda: {"ok": True, "cancelled": 2})
    closes = []
    monkeypatch.setattr(P, "close_spread_via_cli",
                        lambda s, reason, dry_run=False: closes.append(reason) or {"spread": s.key(), "reason": reason})

    result = P.flatten_all_positions(dry_run=False)
    assert result["ok"] and result["flattened"]
    assert len(result["closed"]) == 1
    assert "flatten" in closes[0]


def test_flatten_cancels_resting_orders(monkeypatch):
    """A halt that leaves a working limit at the broker is not a halt — it can still fill
    minutes after the operator pulled the switch."""
    import src.positions as P

    monkeypatch.setattr(P, "fetch_open_spreads", lambda: ([], None))
    monkeypatch.setattr(P, "cancel_open_orders", lambda: {"ok": True, "cancelled": 3})
    result = P.flatten_all_positions(dry_run=False)
    assert result["cancelled_orders"]["cancelled"] == 3


def test_flatten_reports_failure_rather_than_claiming_success(monkeypatch):
    import src.positions as P

    monkeypatch.setattr(P, "cancel_open_orders", lambda: {"ok": True, "cancelled": 0})
    monkeypatch.setattr(P, "fetch_open_spreads", lambda: ([], "broker unreachable"))
    result = P.flatten_all_positions(dry_run=False)
    assert not result["ok"]
    assert "broker unreachable" in result["error"]


# --- take-profit measured against cost ---------------------------------------------------
# The first version measured every structure against max_profit, which made the exit dead
# code for long verticals: an 8-wide spread bought for 1.85 needs to more than double before
# half of max profit is reached, and a 7-DTE position does not get there.

def test_debit_spread_take_profit_is_measured_against_what_was_paid():
    from src.positions import evaluate_exits

    cfg = {"stop_loss_pct_of_max_loss": 0.60,
           "take_profit_pct_of_max_profit": 0.50,
           "take_profit_pct_of_debit_paid": 0.75}
    # paid 200, up 160 = +80% on cost, but only 160/600 = 27% of max profit
    spread = _debit_spread(unrealized_pl=160.0, paid=200.0, width=8.0)
    decision = evaluate_exits([spread], cfg)[0]
    assert decision.should_close
    assert "on debit paid" in decision.reason


def test_the_old_max_profit_threshold_alone_would_not_have_fired():
    """Regression guard for the actual defect: the same winning position, with only the
    max-profit rule configured, is held."""
    from src.positions import evaluate_exits

    cfg = {"stop_loss_pct_of_max_loss": 0.60, "take_profit_pct_of_max_profit": 0.50}
    spread = _debit_spread(unrealized_pl=160.0, paid=200.0, width=8.0)
    assert not evaluate_exits([spread], cfg)[0].should_close


def test_below_the_cost_target_is_still_held():
    from src.positions import evaluate_exits

    cfg = {"stop_loss_pct_of_max_loss": 0.60, "take_profit_pct_of_debit_paid": 0.75}
    spread = _debit_spread(unrealized_pl=80.0, paid=200.0, width=8.0)  # +40% on cost
    assert not evaluate_exits([spread], cfg)[0].should_close


def test_gain_vs_cost_is_none_for_credit_structures():
    """A credit spread's upside IS the credit, so max_profit already measures it correctly
    and applying a cost multiple would be meaningless."""
    from src.positions import Leg, Spread
    from datetime import date

    credit = Spread(
        underlying="SPY", expiry=date(2026, 9, 8),
        legs=[
            Leg("SPY260908P00760000", "SPY", date(2026, 9, 8), "P", 760.0, -1, -150.0, -100.0, 50.0),
            Leg("SPY260908P00752000", "SPY", date(2026, 9, 8), "P", 752.0, 1, 0.0, 0.0, 0.0),
        ],
    )
    assert credit.net_cost_basis < 0
    assert credit.gain_vs_cost is None


# --- resting orders count as claimed exposure --------------------------------------------

def test_multi_leg_order_symbols_come_from_the_legs(monkeypatch):
    """A DIA spread rested unfilled at 16:40 and a second order for the same two legs went in
    at 18:10, because one_position_per_underlying reads positions and a working order is not
    one. MLEG orders carry their symbols on the legs, not on the order itself, so parsing the
    top level alone finds nothing and the name still looks free."""
    import src.alpaca_cli as C

    payload = [{
        "id": "abc",
        "symbol": None,
        "legs": [
            {"symbol": "DIA260911P00526000"},
            {"symbol": "DIA260911P00519000"},
        ],
    }]
    monkeypatch.setattr(C, "_run", lambda *a, **k: C.CliResult(ok=True, stdout=__import__("json").dumps(payload)))
    roots, err = C.open_order_underlyings()
    assert err is None
    assert roots == {"DIA"}


def test_unreadable_orders_do_not_silently_claim_everything(monkeypatch):
    import src.alpaca_cli as C

    monkeypatch.setattr(C, "_run", lambda *a, **k: C.CliResult(ok=False, error="cli down"))
    roots, err = C.open_order_underlyings()
    assert roots == set()
    assert "cli down" in err
