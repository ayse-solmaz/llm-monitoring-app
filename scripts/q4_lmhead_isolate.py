"""Offline lm_head / tied-embed isolate: hidden @ W for q0 vs q4-dequant.

Does NOT touch prod. Pure numpy. Reuses dequant from q4_tensor_hunt.

Modes:
  1) Random hidden (--seed): prior experiment → KERNEL_OR_ACTIVATION_PATH
  2) Captured hidden (--hidden-npy one or more): cross-matmul table
       q0_h @ q0_W, q0_h @ q4_W, q4_h @ q0_W, q4_h @ q4_W
     to separate activation drift vs weight/kernel path.

Usage (repo root):
  python scripts/q4_lmhead_isolate.py --seed 0
  python scripts/q4_lmhead_isolate.py \\
    --hidden-npy backups/last-hidden-q0f16-step4.npy \\
                 backups/last-hidden-q4f32-step4.npy \\
    --hidden-labels q0_hidden q4_hidden \\
    --out backups/q4-lmhead-isolate-captured.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q4_tensor_hunt import (  # noqa: E402
    DEFAULT_Q0,
    DEFAULT_Q4,
    dequant_group_nk,
    load_index,
    load_tensor,
)

HIDDEN = 2048
VOCAB_PROBE = (1, 107)
CHUNK = 8192


def _load_q0_embed(q0_dir: Path) -> np.ndarray:
    idx = load_index(q0_dir)
    rec = idx["model.embed_tokens.weight"]
    w = load_tensor(q0_dir, rec).astype(np.float32)
    if w.shape[1] != HIDDEN:
        raise ValueError(f"q0 embed shape {w.shape}, expected (*, {HIDDEN})")
    return w


def _load_q4_embed_dequant(q4_dir: Path) -> np.ndarray:
    idx = load_index(q4_dir)
    qw = load_tensor(q4_dir, idx["model.embed_tokens.q_weight"])
    qs = load_tensor(q4_dir, idx["model.embed_tokens.q_scale"])
    w = dequant_group_nk(qw, qs).astype(np.float32)
    if w.shape[1] != HIDDEN:
        raise ValueError(f"q4 dequant embed shape {w.shape}, expected (*, {HIDDEN})")
    return w


def logits_from_hidden(weight: np.ndarray, hidden: np.ndarray) -> np.ndarray:
    """logits[v] = weight[v] @ hidden  (== hidden @ W.T). Chunked for RAM."""
    h = hidden.astype(np.float32).ravel()
    if h.size != HIDDEN:
        raise ValueError(f"hidden size {h.size}, expected {HIDDEN}")
    n = weight.shape[0]
    out = np.empty(n, dtype=np.float32)
    for i in range(0, n, CHUNK):
        sl = weight[i : i + CHUNK]
        out[i : i + CHUNK] = sl @ h
    return out


def summarize(logits: np.ndarray, label: str) -> dict[str, Any]:
    argmax = int(np.argmax(logits))
    mx = float(logits[argmax])
    l107 = float(logits[107])
    l1 = float(logits[1])
    return {
        "label": label,
        "logit107": l107,
        "logit1": l1,
        "argmax": argmax,
        "logit_argmax": mx,
        "margin107": l107 - mx,
    }


def _pair_conclusion(s0: dict[str, Any], s4: dict[str, Any]) -> str:
    delta_m = s4["margin107"] - s0["margin107"]
    delta_l107 = s4["logit107"] - s0["logit107"]
    if abs(delta_l107) > 1.0 or abs(delta_m) > 1.0:
        return "STORED_QUANT_SUFFICIENT"
    return "KERNEL_OR_ACTIVATION_PATH"


def _branch_from_cross(cross: dict[str, Any]) -> str:
    """Interpret cross-matmul for activation vs fused-kernel vs weight."""
    # Keys like q0_hidden__q0_W, q0_hidden__q4_W, ...
    q0h_q0w = cross.get("q0_hidden__q0_W") or cross.get("h0__q0_W")
    q0h_q4w = cross.get("q0_hidden__q4_W") or cross.get("h0__q4_W")
    q4h_q0w = cross.get("q4_hidden__q0_W") or cross.get("h4__q0_W")
    q4h_q4w = cross.get("q4_hidden__q4_W") or cross.get("h4__q4_W")

    # Prefer labels containing q0/q4_hidden
    def _find(substr_h: str, substr_w: str) -> dict[str, Any] | None:
        for k, v in cross.items():
            if substr_h in k and substr_w in k:
                return v
        return None

    q0h_q0w = _find("q0", "q0_W") or q0h_q0w
    q0h_q4w = _find("q0", "q4_W") or q0h_q4w
    q4h_q0w = _find("q4", "q0_W") or q4h_q0w
    q4h_q4w = _find("q4", "q4_W") or q4h_q4w

    if not all(isinstance(x, dict) for x in (q0h_q0w, q0h_q4w, q4h_q0w, q4h_q4w)):
        return "INCOMPLETE_CROSS"

    assert q0h_q0w and q0h_q4w and q4h_q0w and q4h_q4w

    # Compare margin107 to runtime reference (~0 vs ~-1.8)
    # Activation drift: q4_h @ q0_W already has bad margin vs q0_h @ q0_W
    act_gap = q4h_q0w["margin107"] - q0h_q0w["margin107"]
    # Weight path: q0_h @ q4_W breaks vs q0_h @ q0_W
    wt_gap = q0h_q4w["margin107"] - q0h_q0w["margin107"]
    # Offline same-model: q4_h @ q4_W vs q0_h @ q0_W
    both_gap = q4h_q4w["margin107"] - q0h_q0w["margin107"]

    # Live gap is ~-1.8 on margin107
    thresh = 1.0
    if abs(act_gap) >= thresh and abs(wt_gap) < thresh:
        return "ACTIVATION_DRIFT"
    if abs(wt_gap) >= thresh and abs(act_gap) < thresh:
        return "WEIGHT_OR_DEQUANT_MATH"
    if abs(act_gap) < thresh and abs(wt_gap) < thresh and abs(both_gap) < thresh:
        # Offline cannot reproduce -1.8 → live fused kernel differs from offline dequant@matmul
        return "FUSED_KERNEL"
    if abs(act_gap) >= thresh and abs(wt_gap) >= thresh:
        return "BOTH_ACTIVATION_AND_WEIGHT"
    return "MIXED_OR_UNCLEAR"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--q0", type=Path, default=DEFAULT_Q0)
    ap.add_argument("--q4", type=Path, default=DEFAULT_Q4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--hidden-npy",
        type=Path,
        nargs="*",
        default=None,
        help="One or more .npy last-hidden vectors (2048,). Enables cross-matmul.",
    )
    ap.add_argument(
        "--hidden-labels",
        nargs="*",
        default=None,
        help="Labels for --hidden-npy (default: h0 h1 ... or q0_hidden/q4_hidden if 2 files)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSON report path (default depends on mode)",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    use_captured = bool(args.hidden_npy)

    if args.out is None:
        args.out = Path(
            "backups/q4-lmhead-isolate-captured.json"
            if use_captured
            else "backups/q4-lmhead-isolate.json"
        )
    out = args.out if args.out.is_absolute() else root / args.out

    print("loading q0 embed …", flush=True)
    w0 = _load_q0_embed(args.q0 if args.q0.is_absolute() else root / args.q0)
    print("  shape", w0.shape, flush=True)
    print("loading + dequant q4 embed …", flush=True)
    w4 = _load_q4_embed_dequant(args.q4 if args.q4.is_absolute() else root / args.q4)
    print("  shape", w4.shape, flush=True)

    runtime_ref = {
        "source": "backups/raw-logit-margin-compare.json step4",
        "q0_margin107": 0.0,
        "q4_margin107": -1.8000085353851318,
    }

    if not use_captured:
        rng = np.random.default_rng(args.seed)
        hidden = rng.standard_normal(HIDDEN, dtype=np.float32)
        hidden = hidden / (np.linalg.norm(hidden) + 1e-8) * float(np.sqrt(HIDDEN))

        print("matmul q0 …", flush=True)
        l0 = logits_from_hidden(w0, hidden)
        print("matmul q4-dequant …", flush=True)
        l4 = logits_from_hidden(w4, hidden)

        s0 = summarize(l0, "q0_float_embed")
        s4 = summarize(l4, "q4_dequant_embed")
        delta_m = s4["margin107"] - s0["margin107"]
        delta_l107 = s4["logit107"] - s0["logit107"]
        conclusion = _pair_conclusion(s0, s4)

        report: dict[str, Any] = {
            "mode": "random_hidden",
            "seed": args.seed,
            "hidden_norm": float(np.linalg.norm(hidden)),
            "hidden_size": HIDDEN,
            "probe_tokens": list(VOCAB_PROBE),
            "q0": s0,
            "q4": s4,
            "delta_logit107_q4_minus_q0": delta_l107,
            "delta_margin107_q4_minus_q0": delta_m,
            "abs_logit_diff_mean": float(np.mean(np.abs(l4 - l0))),
            "abs_logit_diff_max": float(np.max(np.abs(l4 - l0))),
            "abs_logit_diff_p99": float(np.percentile(np.abs(l4 - l0), 99)),
            "conclusion": conclusion,
            "note": (
                "Random seed hidden (not DebugChat step-4). "
                "If |delta_logit107| and |delta_margin107| stay <<1.8, "
                "stored embed quant is NOT enough to explain the runtime -1.8 gap."
            ),
            "runtime_reference": runtime_ref,
        }
    else:
        paths = [p if p.is_absolute() else root / p for p in args.hidden_npy]
        if args.hidden_labels and len(args.hidden_labels) == len(paths):
            labels = list(args.hidden_labels)
        elif len(paths) == 2:
            labels = ["q0_hidden", "q4_hidden"]
        else:
            labels = [f"h{i}" for i in range(len(paths))]

        hiddens: dict[str, np.ndarray] = {}
        for lab, p in zip(labels, paths):
            h = np.load(p).astype(np.float32).reshape(-1)
            if h.size != HIDDEN:
                raise ValueError(f"{p}: size {h.size}, expected {HIDDEN}")
            hiddens[lab] = h
            print(f"loaded {lab} from {p} norm={np.linalg.norm(h):.4f}", flush=True)

        # pairwise hidden distance if both present
        hidden_cmp: dict[str, Any] = {}
        if len(hiddens) >= 2:
            labs = list(hiddens.keys())
            a, b = hiddens[labs[0]], hiddens[labs[1]]
            hidden_cmp = {
                "pair": [labs[0], labs[1]],
                "l2": float(np.linalg.norm(a - b)),
                "cosine": float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8)),
                "max_abs": float(np.max(np.abs(a - b))),
                "mean_abs": float(np.mean(np.abs(a - b))),
            }

        weights = {"q0_W": w0, "q4_W": w4}
        cross: dict[str, Any] = {}
        for hlab, h in hiddens.items():
            for wlab, w in weights.items():
                key = f"{hlab}__{wlab}"
                print(f"matmul {key} …", flush=True)
                logits = logits_from_hidden(w, h)
                cross[key] = summarize(logits, key)

        branch = _branch_from_cross(cross)

        # Same-hidden q0 vs q4 W deltas per hidden
        per_hidden: dict[str, Any] = {}
        for hlab, h in hiddens.items():
            s0 = cross[f"{hlab}__q0_W"]
            s4 = cross[f"{hlab}__q4_W"]
            per_hidden[hlab] = {
                "delta_logit107_q4W_minus_q0W": s4["logit107"] - s0["logit107"],
                "delta_margin107_q4W_minus_q0W": s4["margin107"] - s0["margin107"],
                "pair_conclusion": _pair_conclusion(s0, s4),
            }

        report = {
            "mode": "captured_hidden_cross",
            "hidden_paths": {lab: str(p) for lab, p in zip(labels, paths)},
            "hidden_norms": {lab: float(np.linalg.norm(h)) for lab, h in hiddens.items()},
            "hidden_compare": hidden_cmp,
            "hidden_size": HIDDEN,
            "probe_tokens": list(VOCAB_PROBE),
            "cross_matmul": cross,
            "per_hidden_weight_delta": per_hidden,
            "branch": branch,
            "conclusion": branch,
            "note": (
                "Cross table: rows=captured last-hidden, cols=q0 float W vs offline dequant(q4 W). "
                "ACTIVATION_DRIFT: q4_h @ q0_W already breaks margin vs q0_h @ q0_W. "
                "WEIGHT_OR_DEQUANT_MATH: q0_h @ q4_W breaks. "
                "FUSED_KERNEL: offline cross still fine but live raw logits show -1.8 "
                "(compiled fused_dequantize_NT_matmul ≠ offline dequant+matmul)."
            ),
            "runtime_reference": runtime_ref,
            "interpretation_guide": {
                "ACTIVATION_DRIFT": "gap upstream of lm_head (layers / norms differ → different h)",
                "WEIGHT_OR_DEQUANT_MATH": "stored q4 embed recipe offline differs enough on this h",
                "FUSED_KERNEL": "same h + offline W cannot make -1.8; live fused kernel suspect",
            },
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")
    print(f"CONCLUSION: {report['conclusion']}")


if __name__ == "__main__":
    main()
