"""Dump decode step-N last-hidden (pre lm_head) via DebugChat instrument.

Captures the activation arg feeding:
  q4: fused_dequantize_NT_matmul14  (embed q_weight/q_scale → logits)
  q0: NT_matmul14                   (float embed → logits)

Shape dumped: (2048,) float32 — arg with shape (1,1,2048) on that call.
Also records runtime logits at that step for cross-check vs offline matmul.

Diag / local only — never point at prod :8080 / mlc-model.

Usage (inside mlc-server-spike, mem ≥12g):
  python /scripts/q4_dump_last_hidden.py \\
    --model /model --label q4f32 \\
    --out-npy /out/last-hidden-q4f32-step4.npy \\
    --out-meta /out/last-hidden-q4f32-step4.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import tvm

from q4_raw_logit_margin import (  # noqa: E402
    EOT_ID,
    PROMPT,
    _as_1d_logits,
    _patch_tvm_asnumpy_alias,
    summarize_step,
)

HIDDEN = 2048
VOCAB = 256000

# Tied-embed lm_head kernels (string-scan + probe confirmed for decode).
LMHEAD_NAMES = (
    "fused_dequantize_NT_matmul14",
    "fused_dequantize_NT_matmul9",
    "fused_dequantize_NT_matmul4",
    "NT_matmul14",
    "NT_matmul9",
    "NT_matmul4",
)


class LastHiddenInstrument:
    """Armed only for the target decode step; otherwise a cheap no-op."""

    def __init__(self) -> None:
        self.armed = False
        self.captures: list[dict[str, Any]] = []

    def __call__(self, func, name, before_run, ret_val, *args):  # noqa: ANN001
        if before_run or not self.armed:
            return
        if name not in LMHEAD_NAMES:
            return

        shapes: list[tuple[int, tuple[int, ...], str]] = []
        hidden = None
        logits_buf = None
        for i, a in enumerate(args):
            if not isinstance(a, tvm.runtime.Tensor):
                continue
            sh = tuple(int(x) for x in a.shape)
            shapes.append((i, sh, str(a.dtype)))
            n = int(np.prod(sh))
            # activation into lm_head
            if sh == (1, 1, HIDDEN) or (n == HIDDEN and "float" in str(a.dtype)):
                # prefer exact (1,1,2048); keep last float2048 if several
                if sh == (1, 1, HIDDEN) or hidden is None:
                    arr = a.numpy().astype(np.float32).reshape(-1)
                    if arr.size == HIDDEN:
                        hidden = arr.copy()
            # logits output buffer (post-run, filled)
            if VOCAB in sh or n == VOCAB:
                logits_buf = a.numpy().astype(np.float32).reshape(-1).copy()

        self.captures.append(
            {
                "func_name": name,
                "shapes": [{"arg": i, "shape": list(sh), "dtype": dt} for i, sh, dt in shapes],
                "hidden": hidden,
                "logits_from_buf": logits_buf,
            }
        )


def run_dump(
    model: str,
    model_lib: str,
    *,
    prompt: str,
    target_step: int,
    debug_dir: Path,
) -> tuple[np.ndarray, dict[str, Any]]:
    from mlc_llm.testing.debug_chat import DebugChat

    _patch_tvm_asnumpy_alias()
    debug_dir.mkdir(parents=True, exist_ok=True)
    inst = LastHiddenInstrument()
    dc = DebugChat(
        model=model,
        model_lib=model_lib,
        debug_dir=debug_dir,
        device="cpu",
        debug_instrument=inst,
    )

    steps_meta: list[dict[str, Any]] = []
    out_tokens: list[int] = []

    data_inputs = dc._preprocess_prompts(prompt)  # noqa: SLF001
    embedding, input_len = dc._embed(data_inputs)  # noqa: SLF001
    logits, kv_caches = dc._prefill(embedding, input_len)  # noqa: SLF001

    row = summarize_step(_as_1d_logits(logits), dc.tokenizer)
    row["step"] = 0
    row["phase"] = "prefill"
    steps_meta.append(row)
    next_token = row["chosen_id"]
    out_tokens.append(next_token)

    captured_hidden: np.ndarray | None = None
    captured_detail: dict[str, Any] | None = None
    runtime_logits: np.ndarray | None = None

    for i in range(max(target_step, 1)):
        if next_token in dc.conversation.stop_token_ids and i + 1 < target_step:
            break
        step = i + 1
        inst.armed = step == target_step
        inst.captures.clear()
        logits = dc._decode(next_token, kv_caches)  # noqa: SLF001
        logits_1d = _as_1d_logits(logits)
        row = summarize_step(logits_1d, dc.tokenizer)
        row["step"] = step
        row["phase"] = "decode"
        steps_meta.append(row)

        if step == target_step:
            runtime_logits = logits_1d
            if not inst.captures:
                raise RuntimeError(
                    f"No lm_head matmul capture at step {target_step}. "
                    f"Expected one of {LMHEAD_NAMES}"
                )
            # Prefer matmul14 (vocab-sized); else last capture with hidden
            pick = None
            for c in inst.captures:
                if c["hidden"] is not None and (
                    c["func_name"].endswith("matmul14") or pick is None
                ):
                    pick = c
            if pick is None or pick["hidden"] is None:
                raise RuntimeError(f"Captures lacked hidden: {inst.captures}")
            captured_hidden = pick["hidden"]
            captured_detail = {
                "func_name": pick["func_name"],
                "shapes": pick["shapes"],
                "n_captures": len(inst.captures),
                "all_func_names": [c["func_name"] for c in inst.captures],
            }
            # sanity: instrument logits buf vs VM return
            if pick.get("logits_from_buf") is not None:
                buf = pick["logits_from_buf"]
                if buf.shape == logits_1d.shape:
                    captured_detail["logits_buf_vs_return_max_abs"] = float(
                        np.max(np.abs(buf - logits_1d))
                    )

        next_token = row["chosen_id"]
        out_tokens.append(next_token)
        if next_token in dc.conversation.stop_token_ids and step >= target_step:
            break

    if captured_hidden is None or runtime_logits is None or captured_detail is None:
        raise RuntimeError(f"Failed to capture step {target_step} (got steps {[s['step'] for s in steps_meta]})")

    meta: dict[str, Any] = {
        "prompt": prompt,
        "model": model,
        "model_lib": model_lib,
        "target_step": target_step,
        "hidden_shape": list(captured_hidden.shape),
        "hidden_dtype": "float32",
        "hidden_norm": float(np.linalg.norm(captured_hidden)),
        "hidden_mean": float(np.mean(captured_hidden)),
        "hidden_std": float(np.std(captured_hidden)),
        "dump_source": (
            "DebugChat VM instrument AFTER lm_head call; "
            "arg shape (1,1,2048) into fused_dequantize_NT_matmul14 / NT_matmul14"
        ),
        "capture": captured_detail,
        "generated_ids_through_step": out_tokens[: target_step + 1],
        "generated_text_through_step": dc.tokenizer.decode(out_tokens[: target_step + 1]),
        "step_summary": steps_meta,
        "runtime_logits_at_step": {
            "logit107": float(runtime_logits[EOT_ID]),
            "logit1": float(runtime_logits[1]),
            "argmax": int(np.argmax(runtime_logits)),
            "logit_argmax": float(np.max(runtime_logits)),
            "margin107": float(runtime_logits[EOT_ID] - np.max(runtime_logits)),
        },
    }
    return captured_hidden, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--model-lib", default=None)
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--step", type=int, default=4, help="Decode step index (0=prefill)")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out-npy", default=None)
    ap.add_argument("--out-meta", default=None)
    ap.add_argument("--debug-dir", default="/tmp/mlc-debug-hidden")
    args = ap.parse_args()

    model_lib = args.model_lib or str(Path(args.model) / "gemma-cpu.so")
    if args.step < 1:
        raise SystemExit("--step must be >=1 (prefill has no separate decode lm_head arm)")

    hidden, meta = run_dump(
        args.model,
        model_lib,
        prompt=args.prompt,
        target_step=args.step,
        debug_dir=Path(args.debug_dir),
    )
    meta["label"] = args.label

    out_npy = Path(args.out_npy) if args.out_npy else Path(f"/out/last-hidden-{args.label}-step{args.step}.npy")
    out_meta = (
        Path(args.out_meta)
        if args.out_meta
        else Path(f"/out/last-hidden-{args.label}-step{args.step}.json")
    )
    out_npy.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_npy, hidden.astype(np.float32))
    out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({k: meta[k] for k in (
        "label", "target_step", "hidden_norm", "capture", "runtime_logits_at_step",
        "generated_text_through_step",
    )}, indent=2, ensure_ascii=False))
    print(f"Wrote {out_npy} shape={hidden.shape}")
    print(f"Wrote {out_meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
