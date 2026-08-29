"""
Ties every module together into one trading cycle:
  signals -> live Groq decision + 3 shadow decisions -> risk gate -> execute (or not) -> audit log

Groq is the only path that reaches execution (Alpaca order submission). Claude Code CLI,
Featherless, and Mistral run the same decision every cycle but are shadow-only — their
picks are logged for the model-comparison writeup and never touch the account.
See BRAINSTORM.md section 9 for the full rationale.
"""

import json
import os
from typing import Optional

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from datetime import datetime, timedelta

from src.audit_log import write_cycle_record
from src.decision_schema import SYSTEM_PROMPT, build_user_payload
from src.execution import build_spread, submit_spread_order
from src.model_adapter import call_claude_code_cli, call_openai_compatible
from src.risk_gate import AccountState, TradeProposal, evaluate as evaluate_risk
from src.signals.direction import train_and_predict
from src.signals.iv_rank import compute_vol_signals

SHADOW_PROVIDERS = ["featherless", "mistral"]  # + claude_code_cli, called separately (subprocess, not HTTP)


def get_account_state(trading_client: TradingClient) -> AccountState:
    acct = trading_client.get_account()
    positions = trading_client.get_all_positions()
    open_underlyings = {p.symbol[:3].rstrip("0123456789") if len(p.symbol) > 6 else p.symbol for p in positions}
    # crude open-risk proxy: sum of |market_value| for option positions, refined once real
    # positions exist to track from (currently 0 on a flat dev account)
    open_risk = sum(abs(float(p.market_value)) for p in positions if getattr(p, "asset_class", None) and "option" in str(p.asset_class).lower())
    daily_pnl_pct = (float(acct.equity) - float(acct.last_equity)) / float(acct.last_equity) if float(acct.last_equity) else 0.0
    return AccountState(
        equity=float(acct.equity),
        open_risk_dollars=open_risk,
        open_underlyings=open_underlyings,
        daily_pnl_pct=daily_pnl_pct,
    )


def get_current_price(stock_client: StockHistoricalDataClient, underlying: str) -> float:
    bars = stock_client.get_stock_bars(
        StockBarsRequest(symbol_or_symbols=underlying, timeframe=TimeFrame.Day, start=datetime.now() - timedelta(days=5))
    ).df
    return float(bars["close"].iloc[-1])


def _parse_decision(content: Optional[str]) -> Optional[dict]:
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def run_cycle(underlying: str, dry_run: bool = True) -> dict:
    key, sec = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    opt_client = OptionHistoricalDataClient(key, sec)
    stock_client = StockHistoricalDataClient(key, sec)
    trading_client = TradingClient(key, sec, paper=True)  # literal True — never read from config, see execution notes

    account_state = get_account_state(trading_client)  # fetched once per cycle, always logged —
                                                          # this is the equity-over-time series the dashboard charts
    price = get_current_price(stock_client, underlying)
    vol = compute_vol_signals(opt_client, stock_client, underlying, price)
    direction = train_and_predict(stock_client, underlying)

    if vol is None or direction is None:
        return {"error": "insufficient signal data this cycle", "underlying": underlying}

    signals = {
        "underlying": underlying,
        "current_price": price,
        "classifier_p_up": direction.p_up,
        "iv_rank": vol.iv_rank,
        "iv_percentile": vol.iv_percentile,
        "iv_history_days": vol.iv_history_days,
        "vrp": vol.vrp,
        "market_regime": "HIGH_VOLATILITY" if (vol.iv_rank or 0) > 80 else "NORMAL_VOLATILITY",
        "days_to_earnings": None,  # N/A for SPY/QQQ index ETFs, see blueprint item 3
    }
    payload = build_user_payload(signals)

    # --- live decision (Groq only) ---
    live_result = call_openai_compatible("groq", SYSTEM_PROMPT, payload)
    live_decision = _parse_decision(live_result.content) if live_result.ok else None

    # --- shadow decisions, never executed ---
    shadow_decisions = {}
    for provider in SHADOW_PROVIDERS:
        result = call_openai_compatible(provider, SYSTEM_PROMPT, payload)
        shadow_decisions[provider] = {"ok": result.ok, "decision": _parse_decision(result.content), "error": result.error}

    claude_result = call_claude_code_cli(SYSTEM_PROMPT, payload)
    shadow_decisions["claude_code_cli"] = {"ok": claude_result.ok, "decision": _parse_decision(claude_result.content), "error": claude_result.error}

    # --- risk gate + execution, live decision only ---
    risk_verdict = None
    fill_result = None

    if live_decision and live_decision.get("selected_strategy") not in (None, "cash"):
        spread = build_spread(opt_client, underlying, live_decision["selected_strategy"])
        if spread is None:
            risk_verdict = {"approved": False, "reason": "could not build spread from live chain"}
        else:
            proposal = TradeProposal(
                strategy=spread.strategy,
                underlying=underlying,
                max_profit_per_contract=spread.max_profit_per_contract,
                max_loss_per_contract=spread.max_loss_per_contract,
                classifier_win_probability=direction.p_up,
                llm_confidence_score=live_decision.get("confidence_score", 0.0),
            )
            gate_result = evaluate_risk(proposal, account_state)
            risk_verdict = {"approved": gate_result.approved, "reason": gate_result.reason, "contracts": gate_result.contracts}

            if gate_result.approved and not dry_run:
                order = submit_spread_order(trading_client, spread, gate_result.contracts)
                fill_result = {"order_id": str(order.id), "status": str(order.status)}
            elif gate_result.approved and dry_run:
                fill_result = {"dry_run": True, "would_submit": spread.strategy, "contracts": gate_result.contracts}

    record = write_cycle_record(
        underlying=underlying,
        signals=signals,
        live_decision=live_decision,
        shadow_decisions=shadow_decisions,
        risk_gate_verdict=risk_verdict,
        fill_result=fill_result,
        dry_run=dry_run,
        account_equity=account_state.equity,
    )
    return record


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=True)
    result = run_cycle("SPY", dry_run=True)
    print(json.dumps(result, indent=2, default=str))
