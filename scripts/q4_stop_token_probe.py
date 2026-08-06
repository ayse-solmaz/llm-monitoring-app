"""Stop-token probe for q4 decode divergence.

Goal:
  At divergence step (usually 4), inspect EOS/END_OF_TURN behavior and
  approximate rank(<end_of_turn>) via logit-bias threshold on token 107.

Why threshold instead of exact top-20:
  MLC CPU sampler enforces top_logprobs <= 5, so exact rank>5 is unavailable
  via API. Bias sweep gives a practical rank proxy.
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
PROMPT = "Türkiye'nin başkenti nedir?"
MODEL = "/app/model"

EOS_ID = 1
EOT_ID = 107
TOP_K = 5


def _post(url: str, payload: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_decode(url: str, *, max_tokens: int, seed: int, logit_bias: dict[int, float] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "top_p": 1.0,
        "logprobs": True,
        "top_logprobs": TOP_K,
        "seed": seed,
        "stream": False,
    }
    if logit_bias:
        payload["logit_bias"] = {str(k): float(v) for k, v in logit_bias.items()}
    t0 = time.time()
    body = _post(url, payload)
    sec = round(time.time() - t0, 1)
    choice = body["choices"][0]
    steps = ((choice.get("logprobs") or {}).get("content")) or []
    norm_steps = []
    for i, s in enumerate(steps):
        top = s.get("top_logprobs") or []
        norm_steps.append(
            {
                "i": i,
                "token": s.get("token"),
                "logprob": s.get("logprob"),
                "prob": None if s.get("logprob") is None else float(math.exp(s["logprob"])),
                "top": [
                    {
                        "token": t.get("token"),
                        "logprob": t.get("logprob"),
                        "prob": None if t.get("logprob") is None else float(math.exp(t["logprob"])),
                    }
                    for t in top
                ],
            }
        )
    return {
        "seconds": sec,
        "finish_reason": choice.get("finish_reason"),
        "content": ((choice.get("message") or {}).get("content")) or "",
        "steps": norm_steps,
    }


def find_diverge_idx(q0_decode: dict[str, Any], q4_decode: dict[str, Any]) -> int:
    sa = q0_decode.get("steps") or []
    sb = q4_decode.get("steps") or []
    n = min(len(sa), len(sb))
    for i in range(n):
        if sa[i].get("token") != sb[i].get("token"):
            return i
    return n - 1 if n else 0


def rank_in_top(step: dict[str, Any], token_text: str) -> int | None:
    toks = [t.get("token") for t in (step.get("top") or [])]
    return toks.index(token_text) + 1 if token_text in toks else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:8088")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=8)
    ap.add_argument(
        "--biases",
        default="0,0.5,1,2,4,8,16,32",
        help="comma-separated biases for token 107",
    )
    ap.add_argument("--q0-json", default=str(ROOT / "backups" / "logit-mre-q0f16-decode8.json"))
    ap.add_argument("--q4-json", default=str(ROOT / "backups" / "logit-mre-q4f32-decode8.json"))
    ap.add_argument("--label", default="q4-stop-probe")
    args = ap.parse_args()

    q0_wrap = json.loads(Path(args.q0_json).read_text(encoding="utf-8"))
    q4_wrap = json.loads(Path(args.q4_json).read_text(encoding="utf-8"))
    q0 = q0_wrap["decode"]
    q4 = q4_wrap["decode"]
    div = find_diverge_idx(q0, q4)

    q0_step = q0["steps"][div]
    q4_step = q4["steps"][div]
    base_token = q4_step["token"]

    biases = [float(x.strip()) for x in args.biases.split(",") if x.strip()]
    sweep_rows = []
    for b in biases:
        dec = run_decode(
            args.url,
            max_tokens=args.max_tokens,
            seed=args.seed,
            logit_bias={EOT_ID: b},
        )
        steps = dec.get("steps") or []
        if div >= len(steps):
            sweep_rows.append(
                {
                    "bias_107": b,
                    "error": f"decode too short ({len(steps)} steps), div={div}",
                    "content": dec.get("content"),
                }
            )
            continue
        st = steps[div]
        chosen = st.get("token")
        sweep_rows.append(
            {
                "bias_107": b,
                "chosen_at_diverge_step": chosen,
                "is_eot": chosen == "<end_of_turn>",
                "is_eos": chosen == "<eos>",
                "rank_eot_in_top5": rank_in_top(st, "<end_of_turn>"),
                "rank_eos_in_top5": rank_in_top(st, "<eos>"),
                "rank_base_token_in_top5": rank_in_top(st, base_token),
                "top5": st.get("top"),
                "content": dec.get("content"),
                "finish_reason": dec.get("finish_reason"),
            }
        )

    first_flip = next((r["bias_107"] for r in sweep_rows if r.get("is_eot")), None)

    report = {
        "prompt": PROMPT,
        "diverge_step": div,
        "q0_token_at_diverge": q0_step.get("token"),
        "q4_token_at_diverge": q4_step.get("token"),
        "q0_rank_eot_in_top5": rank_in_top(q0_step, "<end_of_turn>"),
        "q4_rank_eot_in_top5": rank_in_top(q4_step, "<end_of_turn>"),
        "q0_rank_eos_in_top5": rank_in_top(q0_step, "<eos>"),
        "q4_rank_eos_in_top5": rank_in_top(q4_step, "<eos>"),
        "note_topk_limit": "MLC CPU exposes at most top_logprobs=5; exact top20 rank unavailable via API.",
        "first_bias_that_flips_to_eot": first_flip,
        "bias_sweep": sweep_rows,
    }

    out = ROOT / "backups" / f"{args.label}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"diverge_step={div}")
    print(f"q0 token@div={q0_step.get('token')!r} | q4 token@div={q4_step.get('token')!r}")
    print(f"q4 rank(<end_of_turn>) in top5 = {report['q4_rank_eot_in_top5']}")
    print(f"q4 rank(<eos>) in top5 = {report['q4_rank_eos_in_top5']}")
    print(f"first bias that flips q4-><end_of_turn>: {first_flip}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

