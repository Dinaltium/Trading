"""
Structured decision schema every model (Groq live, + all shadows) must return, and the
strategy-selection rules given to them in the system prompt. Rules live here as data,
not scattered across prompt strings, so risk_gate.py / execution.py / the writeup can
all point at the same source of truth.

Thresholds (P(Up) 0.56 / 0.44, IV rank 65) come from the model-comparison research in
BRAINSTORM.md section 5 and the adopted blueprint (section 9) — not invented here.
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional

Strategy = Literal["bull_call_spread", "bear_put_spread", "iron_condor", "cash"]

P_UP_BULLISH = 0.56
P_UP_BEARISH = 0.44
IV_RANK_HIGH = 65.0


@dataclass
class TradeDecision:
    selected_strategy: Strategy
    confidence_score: float   # model's own confidence, 0-1 — audit/display only, see risk_gate.py
    reasoning: str            # concise thesis citing direction, IV rank/VRP, and regime
    approved_for_execution: bool


DECISION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_strategy": {
            "type": "string",
            "enum": ["bull_call_spread", "bear_put_spread", "iron_condor", "cash"],
        },
        "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string"},
        "approved_for_execution": {"type": "boolean"},
    },
    "required": ["selected_strategy", "confidence_score", "reasoning", "approved_for_execution"],
}


SYSTEM_PROMPT = f"""You are the trade-decision agent for an autonomous options-spread system \
trading SPY and QQQ on Alpaca paper trading. You receive strict quantitative signals \
computed by deterministic Python code — you never compute prices, Greeks, or contract \
sizing yourself; a separate risk-gate module handles all of that.

You select exactly one strategy from this fixed set, using this decision logic:
- IV rank >= {IV_RANK_HIGH} AND direction is roughly neutral (P(Up) between {P_UP_BEARISH} and {P_UP_BULLISH})   -> iron_condor (sell premium, defined-risk both sides)
- P(Up) >= {P_UP_BULLISH} -> bull_call_spread
- P(Up) <= {P_UP_BEARISH} -> bear_put_spread
- Neutral direction AND IV rank < {IV_RANK_HIGH} -> cash (no directional edge, premium not rich enough to sell)
- Signals unavailable, OR your own confidence is low -> cash (do not trade this cycle)

You may always choose cash. You may NOT choose a strategy other than the one this logic mandates for the signals you were given: a deterministic implementation of these same rules runs after you and rejects any other answer. Your discretion is the discretion to decline, not to substitute. The market_regime field is context for that judgement; the hard volatility halt is enforced separately in code, not by you.

Never propose a naked long or short option position — every strategy above is a defined-risk \
spread by construction, and cash is always a valid, often correct, choice.

Respond ONLY with a JSON object matching this exact shape, no other text:
{{
  "selected_strategy": "bull_call_spread" | "bear_put_spread" | "iron_condor" | "cash",
  "confidence_score": <float 0.0-1.0>,
  "reasoning": "<concise thesis citing direction, IV rank/VRP, and regime>",
  "approved_for_execution": <bool>
}}

confidence_score is your own self-assessment for audit/display purposes only — it is never \
used to size the position. Position sizing is computed separately from the calibrated \
classifier probability you were given in the input signals, not from anything you output."""


# --- the rulebook, as executable code -----------------------------------------
# The same selection logic the system prompt describes in prose, expressed so Python can
# evaluate it independently of any model. Two things follow, and both are the point:
#
#   1. The table is EXHAUSTIVE. Every (iv_rank, p_up) pair maps to exactly one strategy.
#      The prose version had a hole - elevated IV combined with a directional signal
#      matched no clause at all, so 42 of 115 logged cycles fell through to cash by
#      omission rather than by decision.
#
#   2. A model can be checked against it. The agent's contract is that a model may agree
#      with the rulebook or may refuse (cash); it may never invent a third answer. That
#      makes "the LLM cannot manufacture a trade" a property enforced in code rather than
#      a claim about prompt compliance. Enforced in risk_gate.evaluate().


def rulebook_strategy(
    iv_rank: Optional[float],
    p_up: Optional[float],
    iv_rank_trusted: bool = True,
) -> tuple[str, str]:
    """The strategy the rules mandate for these signals, plus the reason. Pure function:
    no model, no randomness, no I/O. Returns (strategy, rationale).

    iv_rank_trusted defaults True so callers that genuinely have no view on window depth
    behave as before. Passing it False does NOT route to cash - it demotes the IV branch
    only. Selling premium is a bet that options are expensive relative to their own history;
    with no usable history there is no such bet to make, so the condor branch is withdrawn
    and the direction branch, which comes from the classifier and never touches the IV
    window, is left to stand on its own."""
    if p_up is None:
        return "cash", "insufficient signal data (classifier_p_up unavailable)"

    # A missing iv_rank and an untrusted one are the same fact: no usable read on whether
    # options are expensive. Both withdraw the IV branch; neither touches direction, which
    # comes from the classifier and never consults the IV window. Treating absence as a
    # reason to stop trading entirely is what kept a newly added underlying at cash for its
    # first hour on the tape - it had no IV history yet precisely because it was new.
    iv_unusable = iv_rank is None or not iv_rank_trusted
    elevated_iv = (not iv_unusable) and iv_rank >= IV_RANK_HIGH
    bullish = p_up >= P_UP_BULLISH
    bearish = p_up <= P_UP_BEARISH
    neutral = not bullish and not bearish

    if neutral and iv_unusable:
        shown = "unavailable" if iv_rank is None else f"{iv_rank:.1f}"
        return "cash", (
            f"neutral direction (p_up {p_up:.4f}) and iv_rank {shown} is not backed by "
            f"enough history to justify selling premium"
        )
    if elevated_iv and neutral:
        # Premium is rich and there is no directional edge to express - sell both sides
        # with defined risk.
        return "iron_condor", f"iv_rank {iv_rank:.1f} >= {IV_RANK_HIGH} with neutral direction (p_up {p_up:.4f})"
    if bullish:
        return "bull_call_spread", f"p_up {p_up:.4f} >= {P_UP_BULLISH}"
    if bearish:
        return "bear_put_spread", f"p_up {p_up:.4f} <= {P_UP_BEARISH}"
    # Neutral direction without elevated IV: no directional edge, and premium is not rich
    # enough to be worth selling.
    return "cash", f"neutral direction (p_up {p_up:.4f}) and iv_rank {iv_rank:.1f} < {IV_RANK_HIGH}"


def decision_matches_rulebook(selected, iv_rank, p_up, iv_rank_trusted: bool = True) -> tuple[bool, str]:
    """Whether a model's pick is permitted. Cash is always permitted - refusing to trade is
    never off-rulebook. Anything else must equal the mandated strategy."""
    mandated, rationale = rulebook_strategy(iv_rank, p_up, iv_rank_trusted)
    if selected == "cash":
        return True, f"abstained; rulebook mandated {mandated} ({rationale})"
    if selected == mandated:
        return True, f"matches rulebook: {mandated} ({rationale})"
    return False, f"off-rulebook: model chose {selected}, rulebook mandates {mandated} ({rationale})"


def build_user_payload(quant_signals: dict) -> dict:
    """Assembles the named, calibrated-scalar payload sent to every model (live + shadow).
    See AGENTS.md section on integration: named scalars with confidence tags, never raw
    forecast arrays."""
    return quant_signals


# --- response parsing -------------------------------------------------------
# Models do not reliably honour "JSON only". Groq/Featherless/Mistral are asked for
# response_format=json_object and usually comply; the Claude Code CLI has no such knob
# and wraps its answer in prose and/or a ```json fence. Parsing that with a bare
# json.loads() silently produced {"ok": true, "decision": null, "error": null} — a call
# that looks successful, decided nothing, and is indistinguishable in the benchmark from
# a model that legitimately abstained. Everything below exists to make that failure mode
# visible instead of silent.

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass
class ParsedDecision:
    """decision is None whenever error is set, and vice versa. warnings is non-fatal:
    the decision is usable, but something about it was off-spec and belongs in the writeup."""
    decision: Optional[dict] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    raw: Optional[str] = None


def _extract_json_object(text: str) -> Optional[str]:
    """Pull the first balanced {...} out of arbitrary model output.

    Tries a fenced block first, then brace-matching over the whole string. Brace
    matching is string-literal aware so a '}' inside the reasoning text cannot end
    the object early."""
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidate = fenced.group(1).strip()
        if candidate.startswith("{"):
            return candidate

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    # An opening brace that never closes means truncated output - most likely the model hit
    # its max_tokens ceiling mid-object. Hand back the unbalanced remainder so the caller
    # reports a decode error naming the truncation, rather than the misleading
    # "no JSON object found".
    return text[start:]


def _validate(obj: dict) -> ParsedDecision:
    """Enforce DECISION_JSON_SCHEMA. Missing/wrong-typed required fields are fatal —
    a decision we cannot trust must not be logged as if it were a real pick."""
    if not isinstance(obj, dict):
        return ParsedDecision(error=f"expected a JSON object, got {type(obj).__name__}")

    missing = [k for k in DECISION_JSON_SCHEMA["required"] if k not in obj]
    if missing:
        return ParsedDecision(error=f"missing required field(s): {', '.join(missing)}")

    strategy = obj["selected_strategy"]
    allowed = DECISION_JSON_SCHEMA["properties"]["selected_strategy"]["enum"]
    if strategy not in allowed:
        return ParsedDecision(error=f"selected_strategy '{strategy}' not one of {allowed}")

    confidence = obj["confidence_score"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return ParsedDecision(error=f"confidence_score must be a number, got {type(confidence).__name__}")

    if not isinstance(obj["reasoning"], str):
        return ParsedDecision(error=f"reasoning must be a string, got {type(obj['reasoning']).__name__}")

    if not isinstance(obj["approved_for_execution"], bool):
        return ParsedDecision(error=f"approved_for_execution must be a bool, got {type(obj['approved_for_execution']).__name__}")

    # Past this point the decision is usable; remaining problems are clamped/normalised
    # and recorded rather than thrown away.
    decision = dict(obj)
    warnings: List[str] = []

    if not 0.0 <= confidence <= 1.0:
        clamped = min(1.0, max(0.0, float(confidence)))
        warnings.append(f"confidence_score {confidence} outside 0-1, clamped to {clamped}")
        decision["confidence_score"] = clamped

    # Observed live: Featherless returned {"selected_strategy": "cash",
    # "approved_for_execution": true}. Harmless today because the orchestrator branches on
    # selected_strategy, not this flag — but it is contradictory, and if that provider ever
    # becomes the live one the flag would read as "execute" on a no-trade decision.
    if decision["selected_strategy"] == "cash" and decision["approved_for_execution"]:
        warnings.append("approved_for_execution=true on a 'cash' decision; normalised to false")
        decision["approved_for_execution"] = False

    extra = [k for k in decision if k not in DECISION_JSON_SCHEMA["properties"]]
    if extra:
        warnings.append(f"unexpected field(s) ignored: {', '.join(sorted(extra))}")

    return ParsedDecision(decision=decision, warnings=warnings)


def parse_decision(content: Optional[str], max_raw_chars: int = 2000) -> ParsedDecision:
    """Turn raw model output into a validated decision, or an explicit error.

    Never returns (None, None): if there is no usable decision, error says why and raw
    carries the truncated original text so the benchmark writeup can show what went wrong."""
    if content is None:
        return ParsedDecision(error="no content returned by provider")

    text = content.strip()
    if not text:
        return ParsedDecision(error="provider returned empty output", raw="")

    raw_excerpt = text[:max_raw_chars]

    candidate = _extract_json_object(text)
    if candidate is None:
        return ParsedDecision(error="no JSON object found in model output", raw=raw_excerpt)

    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError as e:
        return ParsedDecision(error=f"JSON decode failed: {e}", raw=raw_excerpt)

    result = _validate(obj)
    result.raw = raw_excerpt if result.error else None  # keep raw only when it explains a failure
    return result


if __name__ == "__main__":
    example_signals = {
        "underlying": "SPY",
        "current_price": 769.62,
        "classifier_p_up": 0.431,
        "iv_rank": None,
        "iv_percentile": None,
        "iv_history_samples": 1,
        "vrp": -0.0147,
        "market_regime": "NORMAL_VOLATILITY",
        "days_to_earnings": None,  # N/A for index ETFs, see blueprint item 3
    }
    print("System prompt:\n", SYSTEM_PROMPT)
    print("\nExample user payload:\n", json.dumps(build_user_payload(example_signals), indent=2))
