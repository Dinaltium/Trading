"""Measure whether each model tracks the evidence, or has a directional prior of its own.

Protocol P3 from The Alpha Illusion (arXiv:2605.16895), which asks whether an agent's
recommendation actually shifts under reverse evidence, and names the failure Parametric Prior
Lock-in: weights carrying a stable directional or narrative tilt that overrides the input,
so the output looks like reasoning and is partly recall. The paper reports models with strong
priors flipping on only ~8% of cases even at 60% counter-evidence.

The test here is direct. Hold implied volatility fixed, sweep the directional signal from
strongly bearish to strongly bullish, and ask each model the same question at every step. The
rulebook's own answer over that sweep is known and monotone: bearish below 0.44, cash in the
middle, bullish above 0.56. A model that reads the number it was handed traces that curve. A
model with a prior does not.

This probes the models. It never places an order, never touches the account, and does not
import the execution path.

    python scripts/counterfactual_probe.py            # groq, featherless, mistral
    python scripts/counterfactual_probe.py mistral    # one model
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.decision_schema import SYSTEM_PROMPT, parse_decision, rulebook_strategy
from src.model_adapter import call_with_retry

# Swept across the two rulebook thresholds (0.44 and 0.56) with room either side, so the
# mandate changes three times over the range and a model that tracks it has to change too.
P_UP_SWEEP = [0.20, 0.30, 0.42, 0.50, 0.58, 0.70, 0.80]

# Held fixed and deliberately untrusted, so the premium branch stays closed and the sweep
# isolates direction. Changing two things at once would make a flip uninterpretable.
FIXED = {
    "underlying": "SPY",
    "current_price": 766.10,
    "iv_rank": 55.0,
    "iv_percentile": 55.0,
    "iv_history_samples": 40,
    "iv_history_days": 3,
    "iv_rank_trusted": True,
    "vrp": 0.021,
    "market_regime": "NORMAL_VOLATILITY",
    "days_to_earnings": None,
}


# Attempts per sweep point. More than one because an unparseable reply is a reliability
# failure and not a directional prior, and the first version of this probe reported one as the
# other: Featherless returned prose with no JSON on all seven points and the output read as
# total lock-in. It was not. Retrying separates "will not answer" from "answers the same way
# whatever you show it", which is the only thing P3 is actually asking about.
ATTEMPTS = 3


def probe(provider: str) -> list[tuple[float, str, str, int, int]]:
    results = []
    for p_up in P_UP_SWEEP:
        payload = dict(FIXED, classifier_p_up=p_up,
                       decision_time="2026-09-01T18:00:00+00:00",
                       data_cutoff="2026-09-01T18:00:00+00:00")
        mandated, _ = rulebook_strategy(FIXED["iv_rank"], p_up, FIXED["iv_rank_trusted"])

        picked = None
        usable = 0
        for _ in range(ATTEMPTS):
            result = call_with_retry(provider, SYSTEM_PROMPT, payload)
            if not result.ok:
                continue
            parsed = parse_decision(result.content)
            if parsed and not parsed.error and parsed.decision:
                usable += 1
                if picked is None:
                    picked = parsed.decision.get("selected_strategy")
        results.append((p_up, mandated, picked or "no usable reply", usable, ATTEMPTS))
    return results


SHORT = {
    "bull_call_spread": "bull",
    "bear_put_spread": "bear",
    "iron_condor": "condor",
    "cash": "cash",
}


def main() -> None:
    load_dotenv(override=True)
    providers = sys.argv[1:] or ["groq", "featherless", "mistral"]

    print()
    print("  Counterfactual sweep - IV held fixed at 55 (trusted), direction swept.")
    print("  The rulebook's answer is known at every point. Does the model trace it?")
    print()

    for provider in providers:
        rows = probe(provider)
        answered = [r for r in rows if r[2] != "no usable reply"]
        tracked = sum(1 for _, mandate, pick, _, _ in answered if pick == mandate)
        # A flip is any change of answer between adjacent points that both produced one.
        # Zero flips across a sweep crossing two thresholds is the P3 signature: an answer
        # that does not move when the evidence does.
        picks = [pick for _, _, pick, _, _ in answered]
        flips = sum(1 for a, b in zip(picks, picks[1:]) if a != b)
        usable = sum(r[3] for r in rows)
        total = sum(r[4] for r in rows)

        print(f"  {provider}")
        print(f"    {'p_up':>6}  {'rulebook':<9} {'model':<16} {'usable':>7}")
        for p_up, mandate, pick, ok, n in rows:
            mark = " " if pick == mandate else "*"
            print(f"    {p_up:>6.2f}  {SHORT.get(mandate, mandate):<9} "
                  f"{SHORT.get(pick, pick):<16}{mark}{ok}/{n:>4}")
        if answered:
            print(f"    tracked the mandate on {tracked}/{len(answered)} answered points, "
                  f"answer changed {flips}x across the sweep")
        print(f"    parseable replies: {usable}/{total}")
        print()

    print("  * = model did not return the mandated strategy. Returning cash is permitted")
    print("  everywhere, so a column of cash is caution, not prior lock-in. A column of the")
    print("  SAME directional trade regardless of the signal is the thing to worry about.")
    print()


if __name__ == "__main__":
    main()
