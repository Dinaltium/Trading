"""Score every model against the rulebook, from the live audit log.

This is the measurement the whole shadow-model design exists to produce. Three models receive
an identical signal vector every cycle; one executes and the others are recorded. Because the
rulebook is a pure function of the same two signals, every answer can be marked right or wrong
without knowing the outcome of the trade - compliance is measurable immediately, where
profitability is not measurable for weeks.

Three behaviours are worth separating, and conflating them is the usual mistake:

  compliant   returned the strategy the rulebook mandates
  abstained   returned cash when the rulebook mandated a trade. Permitted, and not an error -
              the model's discretion is exactly the discretion to decline
  off-book    returned some third strategy. This is the failure the gate exists to catch

Relevant literature, because the framing is not ours. Agent Market Arena (arXiv:2510.11695)
reports that "agent frameworks display markedly distinct behavioral patterns ... whereas model
backbones contribute less to outcome variation". This script measures the residual: how much
backbone variation survives when the framework is constrained as hard as it can be, to a
single permitted answer or a refusal.

It is also protocol P6, multi-agent disaggregation, from The Alpha Illusion
(arXiv:2605.16895), which asks for a single-agent baseline and a disagreement rate rather than
an unexamined claim that several models agreeing means something.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "logs" / "audit_log.jsonl"


def load_cycles() -> list[dict]:
    rows = [json.loads(line) for line in LOG.read_text().splitlines() if line.strip()]
    return [r for r in rows if "signals" in r]


def score(cycles: list[dict]) -> dict[str, Counter]:
    stats: dict[str, Counter] = defaultdict(Counter)

    for record in cycles:
        live_provider = record.get("live_provider") or (record.get("live_decision") or {}).get("provider") or "groq"
        entries = [(live_provider, record.get("live_rulebook"))]
        entries += [
            (name, shadow.get("rulebook"))
            for name, shadow in (record.get("shadow_decisions") or {}).items()
        ]

        for name, rulebook in entries:
            if not rulebook:
                # No usable answer: an outage, an unparseable reply, a missing key. Counted
                # separately because a model that cannot answer is not a model that broke a
                # rule, and averaging the two together flatters the unreliable one.
                stats[name]["no_answer"] += 1
                continue
            stats[name]["answered"] += 1
            if rulebook.get("abstained"):
                stats[name]["abstained"] += 1
            elif rulebook.get("compliant"):
                stats[name]["compliant"] += 1
            else:
                stats[name]["off_book"] += 1
    return stats


def disagreement(cycles: list[dict]) -> tuple[int, int]:
    """Cycles where the models did not all pick the same strategy. P6 asks for this rather
    than a bare agreement count: unanimity among models that fail the same way is not
    independent confirmation."""
    split = 0
    total = 0
    for record in cycles:
        picks = {(record.get("live_decision") or {}).get("selected_strategy")}
        for shadow in (record.get("shadow_decisions") or {}).values():
            pick = (shadow.get("decision") or {}).get("selected_strategy")
            if pick:
                picks.add(pick)
        picks.discard(None)
        if len(picks) >= 1:
            total += 1
            if len(picks) > 1:
                split += 1
    return split, total


def main() -> None:
    cycles = load_cycles()
    stats = score(cycles)
    live_cycles = [c for c in cycles if not c.get("dry_run")]

    print()
    print(f"  {len(cycles)} cycles scored   ({len(live_cycles)} live)")
    print()
    # Ordered by off-book rate, which is the only one of these that is a failure. A model
    # that abstains often is cautious, not wrong: the rulebook permits cash unconditionally.
    # Ranking on "compliant / answered" would punish caution and flatter a model that always
    # proposes something, which is the opposite of what this system is built to value.
    print(f"  {'model':16}{'answered':>9}{'mandate':>9}{'abstain':>9}{'off-book':>10}   {'off-book rate':>13}")
    print(f"  {'-'*16}{'-'*9}{'-'*9}{'-'*9}{'-'*10}   {'-'*13}")

    ranked = sorted(
        stats.items(),
        key=lambda kv: (kv[1]["off_book"] / kv[1]["answered"]) if kv[1]["answered"] else 9,
    )
    for name, c in ranked:
        if not c["answered"]:
            print(f"  {name:16}{'-':>9}{'-':>9}{'-':>9}{'-':>10}   {'never answered':>13}")
            continue
        off = c["off_book"] / c["answered"]
        print(
            f"  {name:16}{c['answered']:>9}{c['compliant']:>9}{c['abstained']:>9}"
            f"{c['off_book']:>10}   {off:>12.1%}"
        )

    print()
    print("  abstention rate, the behavioural signature the rulebook makes visible:")
    for name, c in ranked:
        if c["answered"]:
            print(f"    {name:16}{c['abstained']/c['answered']:>6.0%}")

    split, total = disagreement(cycles)
    print()
    print(f"  models disagreed on {split} of {total} cycles ({split/total:.0%})" if total else "")
    print()
    print("  off-book = returned a strategy the rulebook does not mandate. The gate rejects")
    print("  these, so they never trade - but the rate is how often a model tried.")
    print()


if __name__ == "__main__":
    main()
