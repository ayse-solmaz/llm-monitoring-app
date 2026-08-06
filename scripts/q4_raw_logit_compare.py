"""Compare q0 vs q4 raw-logit margin JSON dumps."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
q0 = json.loads((ROOT / "backups/raw-logit-margin-q0f16.json").read_text(encoding="utf-8"))
q4 = json.loads((ROOT / "backups/raw-logit-margin-q4f32.json").read_text(encoding="utf-8"))

print("q0 text:", q0["generated_text"])
print("q4 text:", q4["generated_text"])
print()
hdr = f"{'step':>4} | {'q0_chosen':>14} | {'q0_m107':>8} | {'q4_chosen':>14} | {'q4_m107':>8} | {'d_m107':>8}"
print(hdr)
print("-" * len(hdr))

cmp = []
n = min(len(q0["steps"]), len(q4["steps"]))
for i in range(n):
    a, b = q0["steps"][i], q4["steps"][i]
    d = b["margin_107"] - a["margin_107"]
    print(
        f"{i:>4} | {a['chosen_token'][:14]:>14} | {a['margin_107']:8.3f} | "
        f"{b['chosen_token'][:14]:>14} | {b['margin_107']:8.3f} | {d:8.3f}"
    )
    cmp.append(
        {
            "step": i,
            "q0_chosen": a["chosen_token"],
            "q0_logit_chosen": a["logit_chosen"],
            "q0_logit107": a["logit_107"],
            "q0_logit1": a["logit_1"],
            "q0_margin107": a["margin_107"],
            "q4_chosen": b["chosen_token"],
            "q4_logit_chosen": b["logit_chosen"],
            "q4_logit107": b["logit_107"],
            "q4_logit1": b["logit_1"],
            "q4_margin107": b["margin_107"],
            "delta_margin107_q4_minus_q0": d,
        }
    )

# Also attach q4-only steps after q0 stopped
for i in range(n, len(q4["steps"])):
    b = q4["steps"][i]
    cmp.append(
        {
            "step": i,
            "q0_chosen": None,
            "q4_chosen": b["chosen_token"],
            "q4_logit_chosen": b["logit_chosen"],
            "q4_logit107": b["logit_107"],
            "q4_margin107": b["margin_107"],
        }
    )

out = {
    "prompt": q0["prompt"],
    "q0_text": q0["generated_text"],
    "q4_text": q4["generated_text"],
    "step4": cmp[4] if len(cmp) > 4 else None,
    "steps": cmp,
}
path = ROOT / "backups/raw-logit-margin-compare.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nWrote {path}")
print("\nSTEP4:")
print(json.dumps(out["step4"], ensure_ascii=False, indent=2))
