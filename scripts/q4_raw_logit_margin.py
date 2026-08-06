"""Raw-logit margin MRE (pre LogitProcessor / pre softmax).

Uses MLC DebugChat prefill+decode to capture RAW logits from the compiled
model (same path as serve BatchDecode before InplaceUpdateLogits).

Records per step:
  chosen_id, chosen_token, logit(chosen), logit(107), logit(1),
  max_logit, argmax_id, margin107, margin1

Usage (inside mlc-server-spike container):
  python /scripts/q4_raw_logit_margin.py \\
    --model /model --model-lib /model/gemma-cpu.so \\
    --label q4f32 --out /out/raw-logit-margin-q4f32.json

Host example:
  docker run --rm --memory 12g \\
    -v .../backups/q4f32-weights:/model:ro \\
    -v .../scripts:/scripts:ro \\
    -v .../backups:/out \\
    mlc-server-spike:latest \\
    python3 /scripts/q4_raw_logit_margin.py --model /model --label q4f32
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

EOS_ID = 1
EOT_ID = 107
PROMPT = "Türkiye'nin başkenti nedir?"


def _as_1d_logits(logits) -> np.ndarray:
    arr = logits.numpy() if hasattr(logits, "numpy") else np.asarray(logits)
    arr = np.asarray(arr, dtype=np.float32)
    # shapes seen: (1,1,V) or (1,V) or (V,)
    while arr.ndim > 1:
        arr = arr[0]
    return arr.reshape(-1)


def summarize_step(logits_1d: np.ndarray, tokenizer) -> dict[str, Any]:
    vocab = logits_1d.shape[0]
    chosen_id = int(np.argmax(logits_1d))
    max_logit = float(logits_1d[chosen_id])
    l107 = float(logits_1d[EOT_ID]) if EOT_ID < vocab else float("nan")
    l1 = float(logits_1d[EOS_ID]) if EOS_ID < vocab else float("nan")
    # second-best among non-chosen (for context)
    tmp = logits_1d.copy()
    tmp[chosen_id] = -np.inf
    second_id = int(np.argmax(tmp))
    second_logit = float(logits_1d[second_id])

    try:
        chosen_tok = tokenizer.decode([chosen_id])
    except Exception:  # noqa: BLE001
        chosen_tok = f"id:{chosen_id}"
    try:
        eot_tok = tokenizer.decode([EOT_ID])
    except Exception:  # noqa: BLE001
        eot_tok = "<end_of_turn>"

    return {
        "chosen_id": chosen_id,
        "chosen_token": chosen_tok,
        "logit_chosen": max_logit,
        "logit_107": l107,
        "logit_1": l1,
        "max_logit": max_logit,
        "argmax_id": chosen_id,
        "second_id": second_id,
        "logit_second": second_logit,
        "margin_107": l107 - max_logit,  # negative => 107 behind winner
        "margin_1": l1 - max_logit,
        "margin_107_vs_second": l107 - second_logit,
        "eot_token_text": eot_tok,
        "is_eot": chosen_id == EOT_ID,
        "is_eos": chosen_id == EOS_ID,
    }


def _patch_tvm_asnumpy_alias() -> None:
    """MLC 0.20 DebugChat calls Tensor.asnumpy(); newer TVM only has .numpy()."""
    import tvm

    tensor_cls = getattr(tvm.runtime, "Tensor", None)
    if tensor_cls is not None and not hasattr(tensor_cls, "asnumpy") and hasattr(tensor_cls, "numpy"):
        tensor_cls.asnumpy = tensor_cls.numpy  # type: ignore[attr-defined]


def run_margin(
    model: str,
    model_lib: str,
    *,
    prompt: str,
    max_new_tokens: int,
    debug_dir: Path,
) -> dict[str, Any]:
    from mlc_llm.testing.debug_chat import DebugChat

    _patch_tvm_asnumpy_alias()
    debug_dir.mkdir(parents=True, exist_ok=True)
    # disable instrument: we only need raw decode logits, not full VM dumps
    dc = DebugChat(
        model=model,
        model_lib=model_lib,
        debug_dir=debug_dir,
        device="cpu",
        disable_instrument=True,
    )

    steps: list[dict[str, Any]] = []
    out_tokens: list[int] = []

    data_inputs = dc._preprocess_prompts(prompt)  # noqa: SLF001
    embedding, input_len = dc._embed(data_inputs)  # noqa: SLF001
    logits, kv_caches = dc._prefill(embedding, input_len)  # noqa: SLF001

    # Prefill → first generated token (step 0)
    row = summarize_step(_as_1d_logits(logits), dc.tokenizer)
    row["step"] = 0
    row["phase"] = "prefill"
    steps.append(row)
    next_token = row["chosen_id"]
    out_tokens.append(next_token)

    # Greedy decode further tokens
    for i in range(max_new_tokens - 1):
        if next_token in dc.conversation.stop_token_ids:
            break
        logits = dc._decode(next_token, kv_caches)  # noqa: SLF001
        row = summarize_step(_as_1d_logits(logits), dc.tokenizer)
        row["step"] = i + 1
        row["phase"] = "decode"
        steps.append(row)
        next_token = row["chosen_id"]
        out_tokens.append(next_token)
        if next_token in dc.conversation.stop_token_ids:
            break

    text = dc.tokenizer.decode(out_tokens)
    diverge = next(
        (s["step"] for s in steps if s["chosen_id"] not in (EOT_ID, EOS_ID) and s["step"] >= 4),
        None,
    )
    # Prefer first step where winner is not stop AND margin_107 < 0 after a period-like answer
    first_neg_eot = next((s["step"] for s in steps if s["margin_107"] < 0 and not s["is_eot"]), None)

    return {
        "prompt": prompt,
        "model": model,
        "model_lib": model_lib,
        "max_new_tokens": max_new_tokens,
        "stop_token_ids": list(dc.conversation.stop_token_ids),
        "generated_ids": out_tokens,
        "generated_text": text,
        "first_step_margin107_neg": first_neg_eot,
        "steps": steps,
    }


def print_table(report: dict[str, Any]) -> None:
    print(
        f"{'step':>4} | {'chosen':>16} | {'logit_c':>9} | {'logit107':>9} | "
        f"{'margin107':>9} | {'logit1':>9} | {'margin1':>9}"
    )
    print("-" * 90)
    for s in report["steps"]:
        print(
            f"{s['step']:>4} | {s['chosen_token'][:16]:>16} | {s['logit_chosen']:9.3f} | "
            f"{s['logit_107']:9.3f} | {s['margin_107']:9.3f} | "
            f"{s['logit_1']:9.3f} | {s['margin_1']:9.3f}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, help="MLC model directory")
    ap.add_argument("--model-lib", default=None, help="Path to .so (default: <model>/gemma-cpu.so)")
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--max-new-tokens", type=int, default=8)
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", default=None)
    ap.add_argument("--debug-dir", default="/tmp/mlc-debug-margin")
    args = ap.parse_args()

    model_lib = args.model_lib or str(Path(args.model) / "gemma-cpu.so")
    report = run_margin(
        args.model,
        model_lib,
        prompt=args.prompt,
        max_new_tokens=args.max_new_tokens,
        debug_dir=Path(args.debug_dir),
    )
    report["label"] = args.label
    print_table(report)
    print(f"generated_text={report['generated_text']!r}")

    out = Path(args.out) if args.out else Path(f"/out/raw-logit-margin-{args.label}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
