"""Logit MRE: first-token (and short decode) top-logprobs for MLC backends.

Separates:
  Scenario A — first token already diverges  → int4 quality cliff
  Scenario B — first token same, later breaks → runtime decode / KV / sampling

MLC CPU sampler hard-fails if top_logprobs > 5
(see cpp/serve/sampler/cpu_sampler.cc ComputeTopProbs).

Usage:
  # against current diag (:8088), label = q0f16
  python scripts/q4_logit_mre.py --url http://127.0.0.1:8088 --label q0f16

  # after reseeding diag with q4f32
  python scripts/q4_logit_mre.py --url http://127.0.0.1:8088 --label q4f32

  # compare two saved JSON dumps
  python scripts/q4_logit_mre.py --compare backups/logit-mre-q0f16.json backups/logit-mre-q4f32.json

HF reference (Colab) cell is printed by --print-hf-cell.

Prod (:8080) is never touched by this script.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROMPT = "Türkiye'nin başkenti nedir?"
MODEL = "/app/model"
TOP_K = 5  # MLC CPU hard limit


def ask_logprobs(
    url: str,
    *,
    max_tokens: int,
    prompt: str = PROMPT,
    seed: int = 0,
    timeout: int = 900,
) -> dict[str, Any]:
    endpoint = url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "logprobs": True,
        "top_logprobs": TOP_K,
        "seed": seed,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=data, headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    elapsed = time.time() - t0
    choice = body["choices"][0]
    content = ((choice.get("message") or {}).get("content")) or ""
    lp = choice.get("logprobs") or {}
    content_lps = lp.get("content") or []
    steps: list[dict[str, Any]] = []
    for i, step in enumerate(content_lps):
        token = step.get("token")
        logprob = step.get("logprob")
        top = step.get("top_logprobs") or []
        ranked = []
        for t in top:
            ranked.append(
                {
                    "token": t.get("token"),
                    "logprob": t.get("logprob"),
                    "prob": None
                    if t.get("logprob") is None
                    else float(math.exp(t["logprob"])),
                }
            )
        steps.append(
            {
                "i": i,
                "token": token,
                "logprob": logprob,
                "prob": None if logprob is None else float(math.exp(logprob)),
                "top": ranked,
            }
        )
    return {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "seed": seed,
        "temperature": 0.0,
        "top_logprobs": TOP_K,
        "seconds": round(elapsed, 1),
        "content": content,
        "finish_reason": choice.get("finish_reason"),
        "steps": steps,
        "raw_usage": body.get("usage"),
    }


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Compare two logit dumps; classify Scenario A vs B."""
    sa = a.get("steps") or []
    sb = b.get("steps") or []
    n = min(len(sa), len(sb), 8)
    step_rows = []
    first_diverge = None
    for i in range(n):
        ta, tb = sa[i].get("token"), sb[i].get("token")
        same = ta == tb
        if not same and first_diverge is None:
            first_diverge = i
        top_a = {t["token"]: t for t in sa[i].get("top") or []}
        top_b = {t["token"]: t for t in sb[i].get("top") or []}
        shared = sorted(set(top_a) & set(top_b))
        # rank of a's chosen token in b's top list
        b_tokens = [t["token"] for t in (sb[i].get("top") or [])]
        a_in_b = b_tokens.index(ta) if ta in b_tokens else None
        step_rows.append(
            {
                "i": i,
                "token_a": ta,
                "token_b": tb,
                "same": same,
                "prob_a": sa[i].get("prob"),
                "prob_b": sb[i].get("prob"),
                "a_token_rank_in_b_top": a_in_b,
                "shared_top_tokens": shared,
                "top_a": sa[i].get("top"),
                "top_b": sb[i].get("top"),
            }
        )

    if first_diverge is None and len(sa) and len(sb):
        scenario = "SAME_PREFIX"
        note = "Compared steps match on chosen tokens."
    elif first_diverge == 0:
        scenario = "A_FIRST_TOKEN"
        note = "First token already differs -> int4 quality cliff (runtime sampling got a coherent distribution)."
    else:
        scenario = "B_LATER_TOKEN"
        note = (
            f"First diverge at step {first_diverge} -> look at decode/KV/sampling after prefill."
        )

    return {
        "scenario": scenario,
        "note": note,
        "first_diverge": first_diverge,
        "content_a": a.get("content"),
        "content_b": b.get("content"),
        "steps": step_rows,
    }


def print_hf_cell() -> None:
    cell = r'''
# === HF logit MRE (Colab) — same prompt, top-5 first token ===
# Requires merged HF model dir, e.g. ./gemma-merged-fp32 or reload base+LoRA merge.
import math, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "./gemma-merged-fp32"  # or HF id after upload
PROMPT = "Türkiye'nin başkenti nedir?"
TOP_K = 5

tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(
    MODEL, torch_dtype=torch.float32, device_map="cpu"
)
model.eval()

# Gemma instruct chat template (match MLC gemma_instruction)
messages = [{"role": "user", "content": PROMPT}]
if hasattr(tok, "apply_chat_template"):
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
else:
    text = f"<start_of_turn>user\n{PROMPT}<end_of_turn>\n<start_of_turn>model\n"

ids = tok(text, return_tensors="pt")
with torch.no_grad():
    out = model(**ids)
logits = out.logits[0, -1]  # next-token logits
probs = torch.softmax(logits.float(), dim=-1)
top = torch.topk(probs, TOP_K)
rows = []
for p, idx in zip(top.values.tolist(), top.indices.tolist()):
    rows.append({"token": tok.decode([idx]), "token_id": idx, "prob": p, "logprob": math.log(p)})
print("HF top-5 first token:")
for r in rows:
    print(r)
'''
    print(cell.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:8088")
    ap.add_argument("--label", default="run")
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=1,
        help="1 = first-token only; 8 = short decode for Scenario B",
    )
    ap.add_argument("--compare", nargs=2, metavar=("JSON_A", "JSON_B"))
    ap.add_argument("--print-hf-cell", action="store_true")
    args = ap.parse_args()

    if args.print_hf_cell:
        print_hf_cell()
        return 0

    out_dir = ROOT / "backups"
    out_dir.mkdir(exist_ok=True)

    if args.compare:
        a = json.loads(Path(args.compare[0]).read_text(encoding="utf-8"))
        b = json.loads(Path(args.compare[1]).read_text(encoding="utf-8"))
        # Prefer multi-token decode dumps when present
        if "decode" in a:
            a = a["decode"]
        elif "first_token" in a:
            a = a["first_token"]
        if "decode" in b:
            b = b["decode"]
        elif "first_token" in b:
            b = b["first_token"]
        rep = compare(a, b)
        path = out_dir / "logit-mre-compare.json"
        path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"scenario={rep['scenario']}")
        print(rep["note"])
        print(f"content_a={rep['content_a']!r}")
        print(f"content_b={rep['content_b']!r}")
        for s in rep["steps"]:
            mark = "OK" if s["same"] else "DIVERGE"
            print(
                f"  [{s['i']}] {mark} a={s['token_a']!r} ({s['prob_a']}) | "
                f"b={s['token_b']!r} ({s['prob_b']})"
            )
        print(f"Wrote {path}")
        return 0

    print(f"GET logprobs label={args.label} url={args.url} max_tokens={args.max_tokens}")
    try:
        first = ask_logprobs(
            args.url, max_tokens=1, prompt=args.prompt, seed=args.seed
        )
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", "ignore")[:500]
        print(f"HTTP {exc.code}: {err}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    result: dict[str, Any] = {
        "label": args.label,
        "url": args.url,
        "first_token": first,
    }
    print(
        f"first token content={first['content']!r} finish={first['finish_reason']} "
        f"sec={first['seconds']}"
    )
    for t in (first["steps"][0]["top"] if first["steps"] else []):
        print(f"  {t['token']!r:20} prob={t['prob']:.6f} logprob={t['logprob']}")

    if args.max_tokens > 1:
        print(f"short decode max_tokens={args.max_tokens} ...")
        decode = ask_logprobs(
            args.url, max_tokens=args.max_tokens, prompt=args.prompt, seed=args.seed
        )
        result["decode"] = decode
        print(f"decode content={decode['content']!r} finish={decode['finish_reason']}")
        for s in decode["steps"]:
            print(f"  [{s['i']}] {s['token']!r} p={s['prob']}")

    path = out_dir / f"logit-mre-{args.label}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
