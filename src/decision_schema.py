"""
Structured decision schema every model (Groq live, + all shadows) must return, and the
strategy-selection rules given to them in the system prompt. Rules live here as data,
not scattered across prompt strings, so risk_gate.py / execution.py / the writeup can
all point at the same source of truth.

Thresholds (P(Up) 0.56 / 0.44, IV rank 65) come from the model-comparison research in
BRAINSTORM.md section 5 and the adopted blueprint (section 9) — not invented here.
"""

from dataclasses import dataclass
from typing import Literal

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
- IV rank >= {IV_RANK_HIGH} AND direction is roughly neutral (P(Up) between {P_UP_BEARISH} and {P_UP_BULLISH}) \
  -> iron_condor (sell premium, defined-risk both sides)
- IV rank < {IV_RANK_HIGH} AND P(Up) >= {P_UP_BULLISH} -> bull_call_spread
- IV rank < {IV_RANK_HIGH} AND P(Up) <= {P_UP_BEARISH} -> bear_put_spread
- High-volatility regime flag set, OR no signal combination above clearly applies, \
  OR your own confidence is low -> cash (do not trade this cycle)

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


def build_user_payload(quant_signals: dict) -> dict:
    """Assembles the named, calibrated-scalar payload sent to every model (live + shadow).
    See AGENTS.md section on integration: named scalars with confidence tags, never raw
    forecast arrays."""
    return quant_signals


if __name__ == "__main__":
    import json

    example_signals = {
        "underlying": "SPY",
        "current_price": 769.62,
        "classifier_p_up": 0.431,
        "iv_rank": None,
        "iv_percentile": None,
        "iv_history_days": 1,
        "vrp": -0.0147,
        "market_regime": "NORMAL_VOLATILITY",
        "days_to_earnings": None,  # N/A for index ETFs, see blueprint item 3
    }
    print("System prompt:\n", SYSTEM_PROMPT)
    print("\nExample user payload:\n", json.dumps(build_user_payload(example_signals), indent=2))
