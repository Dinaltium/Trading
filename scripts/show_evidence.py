"""Print the two DIA cycles either side of the open-risk fix, side by side.

Exists because the audit log is JSON lines and unreadable in a screenshot, while the thing
it records is worth showing: a risk rule refusing a trade it should have permitted, and the
same trade approved once the arithmetic behind the rule was corrected. Reads the committed
log, computes nothing, and prints only what is already on disk.
"""

import json
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "logs" / "audit_log.jsonl"


def main() -> None:
    rows = [json.loads(line) for line in LOG.read_text().splitlines() if line.strip()]
    dia = [
        r for r in rows
        if r.get("underlying") == "DIA"
        and (r.get("risk_gate_verdict") or {}).get("reason")
    ]
    if not dia:
        print("no DIA records with a risk-gate verdict yet.")
        return

    refused = next((r for r in dia if not r["risk_gate_verdict"]["approved"]), None)
    approved = next((r for r in dia if r["risk_gate_verdict"]["approved"]), None)

    for label, rec in (("REFUSED", refused), ("APPROVED", approved)):
        if not rec:
            continue
        rb = rec.get("live_rulebook") or {}
        rg = rec["risk_gate_verdict"]
        fill = rec.get("fill_result") or {}
        print()
        print(f"  {rec['timestamp'][:19].replace('T', ' ')} UTC   DIA")
        print(f"    signal      p_up {rec['signals']['classifier_p_up']}")
        print(f"    rulebook    {rb.get('rulebook_mandated')}")
        print(f"    risk gate   {label} - {rg['reason']}")
        if fill.get("submitted"):
            print(f"    order       {fill.get('order_id')}")
        if label == "REFUSED":
            print()
            print("    -- open risk was summing |market_value| of every leg, not max loss --")
            print("    -- read ~$16,000 against a true max loss of $5,165  (fix: 42b8929) --")
    print()


if __name__ == "__main__":
    main()
