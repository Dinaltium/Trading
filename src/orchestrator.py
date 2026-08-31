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
from datetime import datetime, timedelta, timezone

from src.agent_state import AgentState
from src.audit_log import write_cycle_record
from src.alpaca_cli import LiveEndpointError, get_broker_state, submit_spread_via_cli
from src.decision_schema import (
    SYSTEM_PROMPT,
    build_user_payload,
    decision_matches_rulebook,
    parse_decision,
    rulebook_strategy,
)
from src.execution import build_spread
from src.guards import (
    check_faithfulness,
    cross_model_agreement,
    reconcile_positions,
    validate_signals,
)
from src.model_adapter import call_claude_code_cli, call_with_retry
from src.risk_gate import AccountState, TradeProposal, evaluate as evaluate_risk
from src.signals.azte import compute_trigger
from src.signals.direction import train_and_predict
from src.signals.iv_rank import compute_vol_signals

# "anthropic" is registered in model_adapter and deliberately NOT in this list. The key
# authenticates and the workspace resolves; the org's credit balance is not spendable on the
# API, so every cycle returned 400 "credit balance is too low". Leaving it in would spend a
# slice of the cycle's 90-second budget on a call that cannot succeed and would write a
# guaranteed failure into every audit record. Re-add the name here once billing is sorted -
# the adapter entry, the workspace header and the tests are already in place.
ALL_HTTP_PROVIDERS = ["groq", "featherless", "mistral"]  # spoken to over HTTP
CLAUDE_CLI_PROVIDER = "claude_code_cli"                  # spoken to via subprocess, not HTTP
# claude_code_cli is deliberately NOT in the cycle's provider set. It shells out to the
# `claude` binary, which exists on a developer laptop and not on the GitHub Actions runner,
# so unattended cycles recorded four providers and got three answers. Claude now reaches the
# benchmark over HTTP as "anthropic". The subprocess wrapper stays for local use.
ALL_PROVIDERS = list(ALL_HTTP_PROVIDERS)
# Any of the four may be the live one — configured in /admin, see src/live_settings.py.
# Whichever is live executes; the remaining three run as shadows in the same cycle.


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


def call_provider(provider: str, payload: dict):
    """One call site for all four models. claude_code_cli is a subprocess; the rest are HTTP.
    Keeping the dispatch here means live vs shadow is decided purely by configured name."""
    if provider == CLAUDE_CLI_PROVIDER:
        return call_claude_code_cli(SYSTEM_PROMPT, payload)
    return call_with_retry(provider, SYSTEM_PROMPT, payload)


def _score_against_rulebook(decision: Optional[dict], iv_rank, p_up, iv_rank_trusted: bool = True) -> Optional[dict]:
    """Every model's pick, live and shadow alike, scored against the same deterministic
    rulebook. This is the benchmark payload: across the competition it answers "which model
    follows the rules, and which one drifts" with counted evidence instead of impressions.

    Recorded for shadows too, even though a shadow decision can never reach the gate."""
    if not decision:
        return None
    selected = decision.get("selected_strategy")
    permitted, detail = decision_matches_rulebook(selected, iv_rank, p_up, iv_rank_trusted)
    mandated, _ = rulebook_strategy(iv_rank, p_up, iv_rank_trusted)
    return {
        "selected": selected,
        "rulebook_mandated": mandated,
        "compliant": permitted,
        "abstained": selected == "cash" and mandated != "cash",
        "detail": detail,
    }


def _shadow_entry(result) -> dict:
    """One shadow model's audit-log entry. `ok` means "this provider produced a usable
    decision", not merely "the HTTP/subprocess call returned 0" — the old version marked
    a call ok whenever the transport succeeded, so unparseable output was logged as a
    success that decided nothing, which is indistinguishable in the benchmark from a
    model that deliberately chose cash."""
    if not result.ok:
        return {"ok": False, "decision": None, "error": result.error}

    parsed = parse_decision(result.content)
    return {
        "ok": parsed.decision is not None,
        "decision": parsed.decision,
        "error": parsed.error,
        "warnings": parsed.warnings or None,
        "raw_output": parsed.raw,  # populated only when parsing failed, so failures are diagnosable
    }


def run_cycle(
    underlying: str,
    dry_run: bool = True,
    live_provider: str = "groq",
    record_history: bool = False,
) -> dict:
    """record_history defaults False so any ad-hoc `python -m src.orchestrator` run exercises
    the full pipeline without appending to the IV history that iv_rank is measured against.
    Only the scheduler sets it True, and only on a real market-hours cycle."""
    key, sec = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    opt_client = OptionHistoricalDataClient(key, sec)
    stock_client = StockHistoricalDataClient(key, sec)
    trading_client = TradingClient(key, sec, paper=True)  # literal True — never read from config, see execution notes

    # Cross-cycle state, loaded from disk. On GitHub Actions every cycle is a new process,
    # so anything held only in memory is lost between cycles — see src/agent_state.py.
    state = AgentState.load()
    cycle_started_at = datetime.now(timezone.utc)
    heartbeat = state.heartbeat(cycle_started_at)

    breaker = state.breaker_tripped

    account_state = get_account_state(trading_client)  # fetched once per cycle, always logged —
                                                          # this is the equity-over-time series the dashboard charts
    price = get_current_price(stock_client, underlying)
    vol = compute_vol_signals(opt_client, stock_client, underlying, price, record_history=record_history)
    direction = train_and_predict(stock_client, underlying)

    if vol is None or direction is None:
        # Previously a bare dict return: no audit record was written at all, so a cycle that
        # died on missing signal data was indistinguishable from one that never ran. The
        # blocked-and-logged guarantee has to hold for the earliest abort too.
        missing = [n for n, v in (("volatility", vol), ("direction", direction)) if v is None]
        return write_cycle_record(
            underlying=underlying,
            signals={"underlying": underlying, "current_price": price},
            live_decision=None,
            shadow_decisions={},
            risk_gate_verdict={
                "approved": False,
                "reason": f"insufficient signal data ({', '.join(missing)}); no model consulted",
            },
            fill_result=None,
            dry_run=dry_run,
            account_equity=account_state.equity,
            live_provider=live_provider,
        )

    signals = {
        "underlying": underlying,
        "current_price": price,
        "classifier_p_up": direction.p_up,
        "iv_rank": vol.iv_rank,
        "iv_percentile": vol.iv_percentile,
        "iv_history_samples": vol.iv_history_samples,  # cycles, not days - see signals/iv_rank.py
        "iv_history_days": vol.iv_history_days,
        "iv_rank_trusted": vol.iv_rank_trusted,
        "vrp": vol.vrp,
        # Regime is gated on the same trust flag. Calling a 14-sample, single-day window
        # HIGH_VOLATILITY put that phrase in front of four models and into the audit log for
        # four days, on the strength of a number that only meant "today is the highest of the
        # few hours we have ever measured".
        "market_regime": (
            "HIGH_VOLATILITY"
            if vol.iv_rank_trusted and (vol.iv_rank or 0) > 80
            else "NORMAL_VOLATILITY"
        ),
        "days_to_earnings": None,  # N/A for SPY/QQQ index ETFs, see blueprint item 3
        # Temporal provenance, per Look-Ahead-Bench (arXiv:2601.13770). The benchmark's
        # finding is that an LLM scored on historical data may be reciting memorised outcomes
        # rather than predicting, which inflates backtested alpha that then evaporates live.
        # This agent is immune by construction — it decides only on data timestamped at or
        # before the decision instant and is scored on outcomes that have not happened yet —
        # but "immune by construction" is a claim, and this field is the evidence for it.
        "decision_time": cycle_started_at.isoformat(),
        "data_cutoff": cycle_started_at.isoformat(),
    }
    # TradeTrap guard 1 of 4 — market intelligence. A malformed signal vector never reaches
    # a model: asked to reason about an impossible number, a model invents a justification
    # for it rather than objecting.
    signal_guard = validate_signals(signals)
    if not signal_guard.passed:
        return write_cycle_record(
            underlying=underlying,
            signals=signals,
            live_decision=None,
            shadow_decisions={},
            risk_gate_verdict={"approved": False, "reason": "signal validation failed; no model consulted"},
            fill_result=None,
            dry_run=dry_run,
            account_equity=account_state.equity,
            live_provider=live_provider,
            guards={"signals": signal_guard.as_record()},
        )

    # AGENTICAITA's selective-activation trigger. Computed and logged every cycle; not
    # enforced — see src/signals/azte.py for why suppressing cycles is the wrong trade
    # with 27 market hours left.
    trigger = compute_trigger(stock_client, underlying)

    payload = build_user_payload(signals)

    # --- live decision (whichever provider is configured active — default groq) ---
    # call_provider() hides the HTTP-vs-subprocess split so the live/shadow split is purely
    # a matter of which name is configured, not which transport a model happens to use.
    live_result = call_provider(live_provider, payload)
    live_parsed = parse_decision(live_result.content) if live_result.ok else None
    live_decision = live_parsed.decision if live_parsed else None
    # A live provider that fails to return a valid decision must not be silently treated as
    # "chose cash" — record why, so an outage or a schema regression is visible in the log.
    live_decision_error = (
        live_result.error if not live_result.ok else live_parsed.error
    )
    live_decision_warnings = live_parsed.warnings if live_parsed else []

    # --- fallback: an unreachable model must not become an unreachable strategy ----------
    # The rulebook is a pure function of two measured signals and needs no model to evaluate.
    # When the live provider fails outright, falling through to cash means a provider outage
    # silently becomes a trading halt - the agent stops taking the trade its own deterministic
    # rules mandate, for a reason that has nothing to do with the market. Groq answered 10/10
    # so far, but a single bad afternoon inside a five-day competition is the whole result.
    #
    # This is strictly narrower than what the model is allowed to do. The fallback can only
    # ever emit the rulebook's own mandate, which is exactly the one strategy a model would
    # have been permitted to choose; it cannot invent an alternative and it cannot size
    # anything. Every downstream gate still runs unchanged - the rulebook check it trivially
    # passes, and then Kelly sizing, the loss caps, the drawdown halt, the premium-selling
    # halt and reconciliation, none of which consult a model either.
    #
    # Faithfulness is skipped deliberately rather than by omission: that guard checks a
    # model's prose against the signals it was handed, and there is no prose here.
    live_decision_fallback = False
    if live_decision is None:
        mandated, rationale = rulebook_strategy(vol.iv_rank, direction.p_up, vol.iv_rank_trusted)
        if mandated != "cash":
            live_decision = {
                "selected_strategy": mandated,
                "confidence_score": 0.0,  # not a model's confidence; nothing here is a model
                "reasoning": (
                    f"DETERMINISTIC FALLBACK - no model reached. Rulebook mandates {mandated}: "
                    f"{rationale}. No LLM contributed to this decision."
                ),
                "approved_for_execution": True,
            }
            live_decision_fallback = True
            # Surfaced in the record, not just in the reasoning string: a cycle that traded
            # without a model must be countable afterwards, not something a reader has to
            # notice by reading prose.
            live_decision_warnings = list(live_decision_warnings or []) + [
                f"deterministic fallback: live provider failed ({live_decision_error}); "
                f"executed rulebook mandate {mandated} with no model in the loop"
            ]

    # --- shadow decisions, never executed — every provider except whichever is live ---
    shadow_decisions = {}
    for provider in ALL_PROVIDERS:
        if provider == live_provider:
            continue
        entry = _shadow_entry(call_provider(provider, payload))
        entry["rulebook"] = _score_against_rulebook(entry["decision"], vol.iv_rank, direction.p_up, vol.iv_rank_trusted)
        shadow_decisions[provider] = entry

    # --- risk gate + execution, live decision only ---
    risk_verdict = None
    fill_result = None
    reconciliation = None  # Guard 4's verdict, kept so a PASSING reconciliation leaves a
                           # trace too. Previously it was a local read once to decide whether
                           # to raise, so a successful check was indistinguishable in the log
                           # from one that never ran.

    # TradeTrap guard 2 of 4 — strategy formulation. A model that quotes a signal value it
    # was never given has fabricated its own input; its conclusion is unsupported even when
    # the strategy happens to be the one the rulebook mandates.
    # Skipped for the deterministic fallback: this guard exists to catch a model quoting a
    # signal value it was never given, and the fallback's text is generated from those very
    # signals rather than reported by anything.
    faithfulness = (
        check_faithfulness(None, signals)
        if live_decision_fallback
        else check_faithfulness((live_decision or {}).get("reasoning"), signals)
    )

    # TradeTrap guard 3 of 4 — cross-validation across the four independent models.
    agreement = cross_model_agreement((live_decision or {}).get("selected_strategy"), shadow_decisions)

    if live_decision and not faithfulness.passed:
        risk_verdict = {
            "approved": False,
            "reason": "faithfulness check failed: " + "; ".join(faithfulness.failures),
        }
    elif live_decision and live_decision.get("selected_strategy") not in (None, "cash"):
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
                # Raw signals, so the gate re-derives the mandated strategy itself rather
                # than trusting the strategy name the model handed it.
                iv_rank=vol.iv_rank,
                classifier_p_up=direction.p_up,
                iv_rank_trusted=vol.iv_rank_trusted,
            )
            gate_result = evaluate_risk(proposal, account_state)
            risk_verdict = {"approved": gate_result.approved, "reason": gate_result.reason, "contracts": gate_result.contracts}

            if gate_result.approved and breaker:
                # Persisted circuit breaker. Latched by a previous PROCESS, not this one —
                # which is the whole reason it lives on disk.
                fill_result = {
                    "submitted": False,
                    "blocked_by": "execution_circuit_breaker",
                    "failures_at_trip": state.breaker_failures_at_trip,
                    "last_error": state.last_execution_error,
                }
            elif gate_result.approved:
                # TradeTrap guard 4 of 4 — portfolio & ledger. Checked at the last possible
                # moment against a second, independent read of broker state: trading on a
                # stale position map is how a diversification cap silently stops capping.
                #
                # Deliberately OUTSIDE the dry_run branch. It used to sit on the live-only
                # path, which meant that in the deployed configuration — every scheduled
                # cycle runs without --live — Guard 4 never executed at all. A guard that
                # only runs in the mode you are not running is not a guard. It is a
                # read-only check, so there is no reason to skip it.
                recon = reconcile_positions(
                    account_state.open_underlyings, account_state.equity, get_broker_state()
                )
                reconciliation = recon.as_record()

                try:
                    if not recon.passed:
                        raise LiveEndpointError("reconciliation failed: " + "; ".join(recon.failures))
                    if dry_run:
                        fill_result = {
                            "dry_run": True,
                            "would_submit": spread.strategy,
                            "contracts": gate_result.contracts,
                            "reconciled": True,
                        }
                        raise StopIteration  # skip the live path without duplicating the except
                    # Submission goes through the Alpaca CLI, which re-verifies the paper
                    # endpoint out-of-process before the order is built. See src/alpaca_cli.py.
                    fill_result = submit_spread_via_cli(spread, gate_result.contracts)
                    if fill_result.get("submitted"):
                        state.record_execution_success(when=datetime.now(timezone.utc).isoformat())
                    else:
                        state.record_execution_failure(str(fill_result.get("error")))
                except StopIteration:
                    pass  # dry run: the gate and all four guards ran, only the order did not
                except LiveEndpointError as e:
                    # Never downgraded to a warning: an unverified endpoint or a failed
                    # reconciliation means no order, in either mode.
                    if not dry_run:
                        state.record_execution_failure(str(e))
                    fill_result = {"submitted": False, "via": "alpaca_cli", "error": str(e)}

    live_rulebook = _score_against_rulebook(live_decision, vol.iv_rank, direction.p_up, vol.iv_rank_trusted)

    guards = {
        "signals": signal_guard.as_record(),
        "faithfulness": faithfulness.as_record(),
        "cross_model_agreement": agreement,
        "reconciliation": reconciliation,  # None when the cycle never reached submission
        "heartbeat": heartbeat,
        "azte_trigger": trigger.as_record(),
        "agent_state": state.as_record(),
    }

    record = write_cycle_record(
        underlying=underlying,
        signals=signals,
        live_decision=live_decision,
        shadow_decisions=shadow_decisions,
        risk_gate_verdict=risk_verdict,
        fill_result=fill_result,
        dry_run=dry_run,
        account_equity=account_state.equity,
        live_provider=live_provider,
        live_decision_error=live_decision_error,
        live_decision_warnings=live_decision_warnings,
        live_rulebook=live_rulebook,
        guards=guards,
    )

    state.note_cycle(cycle_started_at)
    state.save()
    return record


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=True)
    result = run_cycle("SPY", dry_run=True)
    print(json.dumps(result, indent=2, default=str))
