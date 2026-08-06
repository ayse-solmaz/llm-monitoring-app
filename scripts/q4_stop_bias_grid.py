"""EOS(1) x EOT(107) bias-grid for q4 stop collapse.

Classifies each (bias_eos, bias_eot) cell:
  STOP   — finish_reason=stop OR chosen diverge-step token is <end_of_turn>/<eos>
  SALAD  — continues past clean answer with non-stop tokens
  SHORT  — decode shorter than expected (over-bias cut early)

Usage:
  python scripts/q4_stop_bias_grid.py
  python scripts/q4_stop_bias_grid.py --prompts-only
  python scripts/q4_stop_bias_grid.py --url http://127.0.0.1:8088
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MODEL = "/app/model"
EOS_ID = 1
EOT_ID = 107
TOP_K = 5

DEFAULT_PROMPTS = [
    "Türkiye'nin başkenti nedir?",
    "2+2 kaç eder?",
    "Merhaba",
    "Bugün nasılsın?",
    "Paris hangi ülkededir?",
]

# Coarse grid first (fast), then optional fine.
DEFAULT_GRID = [
    (0.0, 0.0),
    (0.0, 0.5),
    (0.0, 1.0),
    (0.0, 2.0),
    (0.5, 0.0),
    (1.0, 0.0),
    (2.0, 0.0),
    (1.0, 1.0),
    (2.0, 2.0),
]


def _post(url: str, payload: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask(
    url: str,
    prompt: str,
    *,
    max_tokens: int,
    seed: int,
    bias_eos: float,
    bias_eot: float,
) -> dict[str, Any]:
    logit_bias: dict[str, float] = {}
    if bias_eos != 0.0:
        logit_bias[str(EOS_ID)] = bias_eos
    if bias_eot != 0.0:
        logit_bias[str(EOT_ID)] = bias_eot

    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "top_p": 1.0,
        "logprobs": True,
        "top_logprobs": TOP_K,
        "seed": seed,
        "stream": False,
    }
    if logit_bias:
        payload["logit_bias"] = logit_bias

    t0 = time.time()
    body = _post(url, payload)
    sec = round(time.time() - t0, 1)
    choice = body["choices"][0]
    content = ((choice.get("message") or {}).get("content")) or ""
    steps_raw = ((choice.get("logprobs") or {}).get("content")) or []
    steps = []
    for i, s in enumerate(steps_raw):
        steps.append(
            {
                "i": i,
                "token": s.get("token"),
                "logprob": s.get("logprob"),
                "prob": None if s.get("logprob") is None else float(math.exp(s["logprob"])),
            }
        )
    return {
        "seconds": sec,
        "finish_reason": choice.get("finish_reason"),
        "content": content,
        "steps": steps,
        "n_steps": len(steps),
    }


def classify(result: dict[str, Any], *, min_answer_tokens: int = 3) -> str:
    finish = result.get("finish_reason")
    steps = result.get("steps") or []
    tokens = [s.get("token") for s in steps]
    if finish == "stop":
        return "STOP"
    if any(t in ("<end_of_turn>", "<eos>") for t in tokens):
        return "STOP"
    if result.get("n_steps", 0) < min_answer_tokens:
        return "SHORT"
    return "SALAD"


def run_grid(
    url: str,
    prompt: str,
    grid: list[tuple[float, float]],
    *,
    max_tokens: int,
    seed: int,
) -> dict[str, Any]:
    cells = []
    for bias_eos, bias_eot in grid:
        print(f"  bias eos={bias_eos} eot={bias_eot} ...", flush=True)
        res = ask(
            url,
            prompt,
            max_tokens=max_tokens,
            seed=seed,
            bias_eos=bias_eos,
            bias_eot=bias_eot,
        )
        label = classify(res)
        tok4 = res["steps"][4]["token"] if len(res["steps"]) > 4 else None
        cells.append(
            {
                "bias_eos": bias_eos,
                "bias_eot": bias_eot,
                "result": label,
                "finish_reason": res["finish_reason"],
                "content": res["content"],
                "token_at_4": tok4,
                "n_steps": res["n_steps"],
                "seconds": res["seconds"],
                "tokens": [s.get("token") for s in res["steps"]],
            }
        )
        print(
            f"    -> {label} finish={res['finish_reason']} "
            f"tok4={tok4!r} content={res['content']!r}",
            flush=True,
        )
    return {"prompt": prompt, "cells": cells}


def summarize_matrix(cells: list[dict[str, Any]]) -> str:
    lines = ["bias(EOS=1) | bias(EOT=107) | Sonuç | tok@4 | content"]
    lines.append("--- | --- | --- | --- | ---")
    for c in cells:
        lines.append(
            f"{c['bias_eos']} | {c['bias_eot']} | {c['result']} | "
            f"{c.get('token_at_4')!r} | {c.get('content')!r}"
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:8088")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=8)
    ap.add_argument("--label", default="q4-bias-grid")
    ap.add_argument(
        "--prompts",
        nargs="*",
        default=None,
        help="override prompt list; default = 5 short prompts",
    )
    ap.add_argument(
        "--single",
        default=None,
        help="run only one prompt (skip multi-prompt set)",
    )
    args = ap.parse_args()

    if args.single:
        prompts = [args.single]
    elif args.prompts:
        prompts = args.prompts
    else:
        prompts = DEFAULT_PROMPTS

    out_dir = ROOT / "backups"
    out_dir.mkdir(exist_ok=True)

    report: dict[str, Any] = {
        "url": args.url,
        "seed": args.seed,
        "max_tokens": args.max_tokens,
        "grid": [{"bias_eos": a, "bias_eot": b} for a, b in DEFAULT_GRID],
        "prompts": [],
    }

    for prompt in prompts:
        print(f"\n=== PROMPT: {prompt!r} ===", flush=True)
        block = run_grid(
            args.url,
            prompt,
            DEFAULT_GRID,
            max_tokens=args.max_tokens,
            seed=args.seed,
        )
        report["prompts"].append(block)
        print(summarize_matrix(block["cells"]))

    # Aggregate: for each cell, how many prompts STOP vs SALAD
    agg: dict[str, dict[str, int]] = {}
    for block in report["prompts"]:
        for c in block["cells"]:
            key = f"eos={c['bias_eos']},eot={c['bias_eot']}"
            agg.setdefault(key, {"STOP": 0, "SALAD": 0, "SHORT": 0})
            agg[key][c["result"]] = agg[key].get(c["result"], 0) + 1
    report["aggregate"] = agg

    path = out_dir / f"{args.label}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {path}")
    print("\n=== AGGREGATE ===")
    for k, v in agg.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
