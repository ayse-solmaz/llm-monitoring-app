"""Follow-up: longer decode + stronger EOT bias for hard prompts."""

from __future__ import annotations

import json
from pathlib import Path

from q4_stop_bias_grid import ask, classify

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:8088"

CASES = [
    ("Paris hangi ülkededir?", [(0.0, 0.0), (0.0, 2.0), (0.0, 4.0), (0.0, 8.0), (2.0, 0.0)]),
    ("Merhaba", [(0.0, 0.0), (0.0, 2.0), (0.0, 4.0), (0.0, 8.0)]),
    ("Bugün nasılsın?", [(0.0, 0.0), (0.0, 2.0), (0.0, 4.0), (0.0, 8.0)]),
]


def main() -> None:
    out = []
    for prompt, grid in CASES:
        print(f"=== {prompt!r}", flush=True)
        block = {"prompt": prompt, "cells": []}
        for be, bt in grid:
            r = ask(URL, prompt, max_tokens=16, seed=0, bias_eos=be, bias_eot=bt)
            lab = classify(r)
            cell = {
                "bias_eos": be,
                "bias_eot": bt,
                "result": lab,
                "finish": r["finish_reason"],
                "content": r["content"],
                "n": r["n_steps"],
                "tokens": [s["token"] for s in r["steps"]],
            }
            block["cells"].append(cell)
            print(
                f"  eos={be} eot={bt} -> {lab} finish={r['finish_reason']} "
                f"n={r['n_steps']} content={r['content']!r}",
                flush=True,
            )
        out.append(block)
    path = ROOT / "backups" / "q4-bias-grid-followup.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
