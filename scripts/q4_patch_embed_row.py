"""Causal MRE: patch q4 tied-embed row(s) and re-check step-4 margin107.

Diag only — copies shards under backups/q4f32-weights-sentra-fix/; never touches
prod (:8080 / mlc-model) or the original backups/q4f32-weights bins in-place
unless --in-place is passed on the copy dir.

Modes
  float_swap  : offline only — replace dequant row with q0 float (proves row causality)
  requant     : re-quantize q0 float row into int4 group_size=32 and write into shard copy

Usage (repo root):
  python scripts/q4_patch_embed_row.py
  python scripts/q4_patch_embed_row.py --rows 191137 141587 --mode both
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q4_tensor_hunt import (  # noqa: E402
    DEFAULT_Q0,
    DEFAULT_Q4,
    GROUP_SIZE,
    ROOT,
    dequant_group_nk,
    load_index,
    load_tensor,
    quantize_group_nk,
)

HIDDEN = 2048
CHUNK = 8192
TOKEN_107 = 107
SENTRA = 191137
DEFAULT_H4 = ROOT / "backups" / "last-hidden-q4f32-step4.npy"
DEFAULT_OUT_DIR = ROOT / "backups" / "q4f32-weights-sentra-fix"
DEFAULT_REPORT = ROOT / "backups" / "q4-sentra-row-patch.json"

# Meta files needed for a runnable diag model dir (optional docker).
META_FILES = (
    "tensor-cache.json",
    "ndarray-cache.json",
    "mlc-chat-config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "tokenizer.model",
    "gemma-cpu.so",
    ".gitattributes",
)


def f32_to_bf16_bytes(arr: np.ndarray) -> bytes:
    """Pack float32 as MLC f32-to-bf16 storage (high 16 bits)."""
    u32 = arr.astype(np.float32).ravel().view(np.uint32)
    u16 = (u32 >> 16).astype(np.uint16)
    return u16.tobytes()


def resolve_token_labels(tokenizer_json: Path, ids: list[int]) -> dict[str, str]:
    raw = json.loads(tokenizer_json.read_text(encoding="utf-8"))
    vocab = raw.get("model", {}).get("vocab") or raw.get("vocab") or {}
    id2 = {int(v): k for k, v in vocab.items()}
    for at in raw.get("added_tokens", []):
        id2[int(at["id"])] = at.get("content", id2.get(int(at["id"]), "?"))
    return {str(i): id2.get(i, "?") for i in ids}


def copy_model_skeleton(src: Path, dst: Path, *, copy_all_shards: bool) -> list[str]:
    """Copy meta + embed shards (0, 2) into dst. Optionally hardlink/copy other shards."""
    dst.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in META_FILES:
        sp = src / name
        if sp.exists():
            shutil.copy2(sp, dst / name)
            copied.append(name)

    # Always copy the two embed shards (we patch these).
    for shard in ("params_shard_0.bin", "params_shard_2.bin"):
        sp = src / shard
        if not sp.exists():
            raise FileNotFoundError(sp)
        dp = dst / shard
        if not dp.exists() or dp.stat().st_size != sp.stat().st_size:
            print(f"copying {shard} ({sp.stat().st_size / 1e6:.1f} MB) …", flush=True)
            shutil.copy2(sp, dp)
        copied.append(shard)

    if copy_all_shards:
        for sp in sorted(src.glob("params_shard_*.bin")):
            if sp.name in ("params_shard_0.bin", "params_shard_2.bin"):
                continue
            dp = dst / sp.name
            if dp.exists() and dp.stat().st_size == sp.stat().st_size:
                continue
            print(f"copying {sp.name} …", flush=True)
            try:
                # Prefer hardlink to save disk; fall back to copy.
                if dp.exists():
                    dp.unlink()
                dp.hardlink_to(sp)
            except OSError:
                shutil.copy2(sp, dp)
            copied.append(sp.name)
    return copied


def patch_row_bytes(
    model_dir: Path,
    row_id: int,
    qw_row: np.ndarray,
    qs_row: np.ndarray,
) -> dict[str, Any]:
    """Write one NK-quantized embed row into q_weight / q_scale shards."""
    idx = load_index(model_dir)
    rec_w = idx["model.embed_tokens.q_weight"]
    rec_s = idx["model.embed_tokens.q_scale"]
    n_storage = int(rec_w.shape[1])  # 256
    n_group = int(rec_s.shape[1])  # 64
    assert qw_row.shape == (n_storage,), qw_row.shape
    assert qs_row.shape == (n_group,), qs_row.shape

    w_off = rec_w.byte_offset + row_id * n_storage * 4
    s_off = rec_s.byte_offset + row_id * n_group * 2  # bf16

    w_path = model_dir / rec_w.data_path
    s_path = model_dir / rec_s.data_path
    with w_path.open("r+b") as f:
        f.seek(w_off)
        f.write(np.ascontiguousarray(qw_row, dtype=np.uint32).tobytes())
    with s_path.open("r+b") as f:
        f.seek(s_off)
        f.write(f32_to_bf16_bytes(qs_row))

    return {
        "row_id": row_id,
        "q_weight_path": rec_w.data_path,
        "q_weight_byte_offset": w_off,
        "q_scale_path": rec_s.data_path,
        "q_scale_byte_offset": s_off,
        "q_scale_format": "f32-to-bf16",
    }


def logits_chunked(qw: np.ndarray, qs: np.ndarray, h: np.ndarray) -> np.ndarray:
    n = qw.shape[0]
    out = np.empty(n, dtype=np.float32)
    for i in range(0, n, CHUNK):
        w = dequant_group_nk(qw[i : i + CHUNK], qs[i : i + CHUNK])
        out[i : i + CHUNK] = w @ h
    return out


def summarize(logits: np.ndarray, label: str) -> dict[str, Any]:
    am = int(np.argmax(logits))
    l107 = float(logits[TOKEN_107])
    mx = float(logits[am])
    return {
        "label": label,
        "argmax": am,
        "logit_argmax": mx,
        "logit107": l107,
        "logit_sentra": float(logits[SENTRA]) if logits.shape[0] > SENTRA else None,
        "margin107": l107 - mx,
        "picks_107": am == TOKEN_107,
    }


def apply_float_swap(
    logits_q4: np.ndarray,
    w0: np.ndarray,
    h: np.ndarray,
    rows: list[int],
) -> np.ndarray:
    out = logits_q4.copy()
    for r in rows:
        out[r] = float(w0[r] @ h)
    return out


def apply_requant_swap(
    qw: np.ndarray,
    qs: np.ndarray,
    w0: np.ndarray,
    rows: list[int],
) -> tuple[np.ndarray, np.ndarray, dict[int, tuple[np.ndarray, np.ndarray]]]:
    qw2 = qw.copy()
    qs2 = qs.copy()
    packed: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for r in rows:
        qwr, qsr = quantize_group_nk(w0[r : r + 1].astype(np.float32))
        qw2[r] = qwr[0]
        qs2[r] = qsr[0]
        packed[r] = (qwr[0], qsr[0])
    return qw2, qs2, packed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--q0", type=Path, default=DEFAULT_Q0)
    ap.add_argument("--q4", type=Path, default=DEFAULT_Q4)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--hidden-npy", type=Path, default=DEFAULT_H4)
    ap.add_argument("--rows", type=int, nargs="+", default=[SENTRA])
    ap.add_argument(
        "--mode",
        choices=("float_swap", "requant", "both"),
        default="both",
        help="float_swap=offline q0 row; requant=write int4 RT into copy",
    )
    ap.add_argument(
        "--copy-all-shards",
        action="store_true",
        help="Also hardlink/copy remaining shards for optional docker DebugChat",
    )
    ap.add_argument(
        "--auto-quant-beaters",
        action="store_true",
        help="Also float-swap every vocab row where q4_logit>logit107 but q0_logit<logit107",
    )
    ap.add_argument("--skip-copy", action="store_true", help="Offline only; do not write shard copy")
    ap.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()

    q0 = args.q0 if args.q0.is_absolute() else ROOT / args.q0
    q4 = args.q4 if args.q4.is_absolute() else ROOT / args.q4
    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    h_path = args.hidden_npy if args.hidden_npy.is_absolute() else ROOT / args.hidden_npy
    report_path = args.out if args.out.is_absolute() else ROOT / args.out

    rows = sorted(set(args.rows))
    h = np.load(h_path).astype(np.float32).ravel()
    if h.size != HIDDEN:
        raise ValueError(f"hidden size {h.size}, expected {HIDDEN}")

    print("loading q0 embed …", flush=True)
    w0 = load_tensor(q0, load_index(q0)["model.embed_tokens.weight"]).astype(np.float32)
    print("loading q4 embed …", flush=True)
    idx4 = load_index(q4)
    qw = load_tensor(q4, idx4["model.embed_tokens.q_weight"])
    qs = load_tensor(q4, idx4["model.embed_tokens.q_scale"]).astype(np.float32)

    tok_path = q4 / "tokenizer.json"
    labels = resolve_token_labels(tok_path, rows + [TOKEN_107]) if tok_path.exists() else {}

    print("baseline logits (chunked dequant) …", flush=True)
    logits_base = logits_chunked(qw, qs, h)
    before = summarize(logits_base, "baseline_q4_dequant")
    am_lab = labels.get(str(before["argmax"]), "?")
    am_lab_safe = am_lab.encode("ascii", "replace").decode("ascii")
    print(
        f"  before: argmax={before['argmax']} ({am_lab_safe}) "
        f"margin107={before['margin107']:.4f}",
        flush=True,
    )

    results: dict[str, Any] = {
        "prod_untouched": True,
        "hidden_npy": str(h_path),
        "rows_patched": rows,
        "row_labels": labels,
        "group_size": GROUP_SIZE,
        "before": before,
        "row_diagnostics": {},
    }

    for r in rows:
        deq = dequant_group_nk(qw[r : r + 1], qs[r : r + 1])[0]
        qwr, qsr = quantize_group_nk(w0[r : r + 1])
        deq_rt = dequant_group_nk(qwr, qsr)[0]
        results["row_diagnostics"][str(r)] = {
            "token": labels.get(str(r), "?"),
            "logit_q4": float(deq @ h),
            "logit_q0": float(w0[r] @ h),
            "logit_requant_rt": float(deq_rt @ h),
            "delta_logit_q4_minus_q0": float(deq @ h - w0[r] @ h),
            "mae_store_vs_q0": float(np.mean(np.abs(deq - w0[r]))),
            "mae_rt_vs_q0": float(np.mean(np.abs(deq_rt - w0[r]))),
            "cosine_store_vs_rt": float(
                np.dot(deq, deq_rt) / (np.linalg.norm(deq) * np.linalg.norm(deq_rt) + 1e-8)
            ),
        }

    after_float = None
    after_requant = None
    disk_patches: list[dict[str, Any]] = []

    if args.mode in ("float_swap", "both"):
        print(f"float_swap rows {rows} …", flush=True)
        logits_f = apply_float_swap(logits_base, w0, h, rows)
        after_float = summarize(logits_f, "float_swap_q0_rows")
        print(
            f"  float_swap: argmax={after_float['argmax']} "
            f"margin107={after_float['margin107']:.4f} picks_107={after_float['picks_107']}",
            flush=True,
        )
        results["after_float_swap"] = after_float

    if args.mode in ("requant", "both"):
        print(f"requant rows {rows} …", flush=True)
        qw2, qs2, packed = apply_requant_swap(qw, qs, w0, rows)
        logits_r = logits_chunked(qw2, qs2, h)
        after_requant = summarize(logits_r, "requant_q0_rows")
        print(
            f"  requant: argmax={after_requant['argmax']} "
            f"margin107={after_requant['margin107']:.4f} picks_107={after_requant['picks_107']}",
            flush=True,
        )
        results["after_requant"] = after_requant

        if not args.skip_copy:
            print(f"writing shard copy → {out_dir}", flush=True)
            copied = copy_model_skeleton(q4, out_dir, copy_all_shards=args.copy_all_shards)
            results["out_dir"] = str(out_dir)
            results["copied_files"] = copied
            for r in rows:
                qwr, qsr = packed[r]
                meta = patch_row_bytes(out_dir, r, qwr, qsr)
                disk_patches.append(meta)
                # verify round-trip read
                idx_p = load_index(out_dir)
                qw_v = load_tensor(out_dir, idx_p["model.embed_tokens.q_weight"])
                qs_v = load_tensor(out_dir, idx_p["model.embed_tokens.q_scale"]).astype(np.float32)
                if not np.array_equal(qw_v[r], qwr):
                    raise RuntimeError(f"q_weight verify failed row {r}")
                if not np.allclose(qs_v[r], qsr, rtol=0, atol=0):
                    # bf16 may lose lsbs vs float32 quantize output
                    if not np.allclose(qs_v[r], qsr, rtol=0, atol=1e-2):
                        raise RuntimeError(f"q_scale verify failed row {r}: {qs_v[r][:4]} vs {qsr[:4]}")
            results["disk_patches"] = disk_patches

            # Re-load patched and confirm offline matches after_requant
            qw_p = load_tensor(out_dir, load_index(out_dir)["model.embed_tokens.q_weight"])
            qs_p = load_tensor(out_dir, load_index(out_dir)["model.embed_tokens.q_scale"]).astype(
                np.float32
            )
            logits_disk = logits_chunked(qw_p, qs_p, h)
            after_disk = summarize(logits_disk, "disk_requant_reload")
            results["after_disk_reload"] = after_disk
            print(
                f"  disk reload: argmax={after_disk['argmax']} margin107={after_disk['margin107']:.4f}",
                flush=True,
            )

    # Causal verdict
    float_pass = bool(after_float and after_float["picks_107"])
    requant_pass = bool(after_requant and after_requant["picks_107"])
    if args.mode == "float_swap":
        causal = "PASS" if float_pass else "FAIL"
    elif args.mode == "requant":
        causal = "PASS" if requant_pass else "FAIL"
    else:
        if float_pass and not requant_pass:
            causal = "PASS_FLOAT_ONLY"
        elif float_pass and requant_pass:
            causal = "PASS"
        elif not float_pass and requant_pass:
            causal = "PASS_REQUANT_ONLY"
        else:
            causal = "FAIL"

    results["causal_verdict"] = causal
    results["causal_note"] = (
        "PASS if patched offline matmul picks token 107. "
        "float_swap replaces dequant row with q0 float; "
        "requant writes int4 RT of q0 into shard copy (often ≡ stored q4)."
    )

    # Suggest extra rows if single-row float fails but sentra logit is fixed
    if after_float and not after_float["picks_107"]:
        logits_f = apply_float_swap(logits_base, w0, h, rows)
        beaters = np.where(logits_f > after_float["logit107"])[0]
        extra_labels = resolve_token_labels(tok_path, [int(i) for i in beaters[:16]]) if tok_path.exists() else {}
        results["remaining_beaters_after_float_swap"] = [
            {
                "id": int(i),
                "token": extra_labels.get(str(int(i)), "?"),
                "logit": float(logits_f[i]),
            }
            for i in beaters[:16]
        ]

    if args.auto_quant_beaters:
        l107_q4 = float(logits_base[TOKEN_107])
        # Rows that beat 107 under q4
        cand = np.where(logits_base > l107_q4)[0]
        print(f"scanning {cand.size} q4-beaters for quant-inflated false winners …", flush=True)
        false_winners: list[int] = []
        for i in cand:
            l0 = float(w0[int(i)] @ h)
            if l0 < l107_q4:
                false_winners.append(int(i))
        print(f"  quant-inflated beaters: {false_winners}", flush=True)
        results["quant_inflated_beaters"] = false_winners
        if false_winners:
            logits_auto = apply_float_swap(logits_base, w0, h, false_winners)
            after_auto = summarize(logits_auto, "float_swap_quant_inflated_beaters")
            results["after_float_swap_quant_inflated"] = after_auto
            print(
                f"  auto float_swap: argmax={after_auto['argmax']} "
                f"margin107={after_auto['margin107']:.4f} picks_107={after_auto['picks_107']}",
                flush=True,
            )
            if after_auto["picks_107"] and results["causal_verdict"] == "FAIL":
                results["causal_verdict"] = "PASS_FLOAT_MULTI_ROW"
                results["causal_note"] += (
                    f" Single-row {rows} insufficient; float-swapping quant-inflated "
                    f"beaters {false_winners} restores 107."
                )
                causal = results["causal_verdict"]

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {report_path}", flush=True)
    print(f"CAUSAL {results['causal_verdict']}", flush=True)


if __name__ == "__main__":
    main()
