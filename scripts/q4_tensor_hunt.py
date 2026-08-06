"""Find first broken tensor: MLC q0f16 (ref) vs dequant(q4).

Pure numpy — no TVM/MLC runtime. Prod untouched.

Hypothesis under test:
  same merge → q0f16 float weights ≈ dequant(group_quant(q4))
  If gap >> expected q4 noise, convert/quantize path is the bug locus.

Usage (repo root):
  python scripts/q4_tensor_hunt.py
  python scripts/q4_tensor_hunt.py --q4 backups/new-weights --label pathA-q4f16
  python scripts/q4_tensor_hunt.py --only-norms
  python scripts/q4_tensor_hunt.py --limit 8
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_Q0 = ROOT / "backups" / "q0f16-weights"
DEFAULT_Q4 = ROOT / "backups" / "q4f32-weights"

# MLC q4f16_1 / q4f32_1 (see vendor/mlc-llm-0.20.0/quantization/quantization.py)
GROUP_SIZE = 32
BITS = 4
NUM_ELEM_PER_STORAGE = 32 // BITS  # 8
MAX_INT = (2 ** (BITS - 1)) - 1  # 7
MASK = (1 << BITS) - 1


@dataclass
class Record:
    name: str
    shape: list[int]
    dtype: str
    format: str
    nbytes: int
    byte_offset: int
    data_path: str


def load_index(model_dir: Path) -> dict[str, Record]:
    cache_path = model_dir / "tensor-cache.json"
    if not cache_path.exists():
        cache_path = model_dir / "ndarray-cache.json"
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    out: dict[str, Record] = {}
    for shard in raw["records"]:
        data_path = shard["dataPath"]
        for r in shard["records"]:
            out[r["name"]] = Record(
                name=r["name"],
                shape=list(r["shape"]),
                dtype=r["dtype"],
                format=r.get("format", "raw"),
                nbytes=int(r["nbytes"]),
                byte_offset=int(r["byteOffset"]),
                data_path=data_path,
            )
    return out


def _np_dtype(dtype: str) -> np.dtype:
    return {
        "float16": np.float16,
        "float32": np.float32,
        "uint32": np.uint32,
        "int32": np.int32,
        "bfloat16": np.uint16,  # storage; decode separately
    }[dtype]


def load_tensor(model_dir: Path, rec: Record) -> np.ndarray:
    """Read one MLC tensor-cache record (handles f32-to-bf16 packed float32)."""
    path = model_dir / rec.data_path
    n_elem = int(np.prod(rec.shape))
    expect_raw = n_elem * np.dtype(_np_dtype(rec.dtype)).itemsize

    with path.open("rb") as f:
        f.seek(rec.byte_offset)
        blob = f.read(rec.nbytes)

    # Integer / exact-size raw
    if rec.dtype.startswith("uint") or rec.dtype.startswith("int"):
        arr = np.frombuffer(blob, dtype=_np_dtype(rec.dtype), count=n_elem)
        return arr.reshape(rec.shape).copy()

    # float32 declared but stored as bf16 (common MLC encode_format)
    if rec.dtype == "float32" and rec.nbytes == n_elem * 2:
        u16 = np.frombuffer(blob, dtype=np.uint16, count=n_elem)
        # bfloat16 → float32: put bits in high 16 of uint32
        f32_bits = u16.astype(np.uint32) << 16
        return np.frombuffer(f32_bits.tobytes(), dtype=np.float32).reshape(rec.shape).copy()

    if rec.dtype == "float16" and rec.nbytes == n_elem * 2:
        arr = np.frombuffer(blob, dtype=np.float16, count=n_elem)
        return arr.reshape(rec.shape).copy()

    if rec.dtype == "float32" and rec.nbytes == n_elem * 4:
        arr = np.frombuffer(blob, dtype=np.float32, count=n_elem)
        return arr.reshape(rec.shape).copy()

    raise ValueError(
        f"Unsupported layout for {rec.name}: dtype={rec.dtype} "
        f"nbytes={rec.nbytes} expect_raw={expect_raw} format={rec.format}"
    )


def dequant_group_nk(q_weight: np.ndarray, q_scale: np.ndarray) -> np.ndarray:
    """Dequantize MLC group-quant NK layout (axis=1), matching group_quantization._dequantize."""
    if q_weight.dtype != np.uint32:
        q_weight = q_weight.astype(np.uint32)
    q_scale = q_scale.astype(np.float32)
    n, n_storage = q_weight.shape
    k = n_storage * NUM_ELEM_PER_STORAGE
    n_group = (k + GROUP_SIZE - 1) // GROUP_SIZE
    if q_scale.shape != (n, n_group):
        raise ValueError(f"scale shape {q_scale.shape} != {(n, n_group)}")

    shifts = (np.arange(NUM_ELEM_PER_STORAGE, dtype=np.uint32) * BITS).reshape(1, 1, -1)
    words = q_weight.reshape(n, n_storage, 1)
    vals = ((words >> shifts) & MASK).astype(np.float32)  # (N, S, 8)
    vals = vals.reshape(n, k)
    group_idx = np.arange(k) // GROUP_SIZE
    return (vals - float(MAX_INT)) * q_scale[:, group_idx]


def quantize_group_nk(weight: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Reference numpy quantize matching GroupQuantize._quantize (NK, axis=1)."""
    w = weight.astype(np.float32)
    n, k = w.shape
    if k % GROUP_SIZE != 0:
        raise ValueError(f"K={k} not divisible by group_size={GROUP_SIZE}")
    n_group = k // GROUP_SIZE
    grouped = w.reshape(n, n_group, GROUP_SIZE)
    max_abs = np.max(np.abs(grouped), axis=-1)  # (N, G)
    scale = max_abs / float(MAX_INT)
    # Avoid div-by-zero in round-trip probe (MLC leaves 0; runtime undefined)
    scale_safe = np.where(scale == 0, 1.0, scale)
    scaled = np.round(w / scale_safe[:, np.arange(k) // GROUP_SIZE] + MAX_INT)
    scaled = np.clip(scaled, 0, MAX_INT * 2).astype(np.uint32)

    n_storage = k // NUM_ELEM_PER_STORAGE
    packed = np.zeros((n, n_storage), dtype=np.uint32)
    for e in range(NUM_ELEM_PER_STORAGE):
        packed |= scaled[:, e::NUM_ELEM_PER_STORAGE] << (e * BITS)
    return packed, scale.astype(np.float32)


def err_stats(ref: np.ndarray, other: np.ndarray) -> dict[str, float]:
    a = ref.astype(np.float32).ravel()
    b = other.astype(np.float32).ravel()
    diff = np.abs(a - b)
    denom = np.maximum(np.abs(a), 1e-8)
    rel = diff / denom
    return {
        "mae": float(diff.mean()),
        "max_abs": float(diff.max()),
        "rms": float(np.sqrt((diff**2).mean())),
        "max_rel": float(rel.max()),
        "p99_abs": float(np.percentile(diff, 99)),
        "frac_rel_gt_0_1": float((rel > 0.1).mean()),
        "frac_rel_gt_0_5": float((rel > 0.5).mean()),
        "ref_max_abs": float(np.abs(a).max()),
        "ref_mean_abs": float(np.abs(a).mean()),
    }


def is_norm(name: str) -> bool:
    return name.endswith("layernorm.weight") or name == "model.norm.weight"


def base_weight_name(q4_name: str) -> str | None:
    if q4_name.endswith(".q_weight"):
        return q4_name[: -len(".q_weight")] + ".weight"
    return None


def hunt(
    q0_dir: Path,
    q4_dir: Path,
    *,
    only_norms: bool = False,
    skip_embed: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    q0 = load_index(q0_dir)
    q4 = load_index(q4_dir)

    rows: list[dict[str, Any]] = []
    norm_rows: list[dict[str, Any]] = []

    # --- RMSNorm / non-quant float params present in both ---
    for name, rec0 in q0.items():
        if not is_norm(name):
            continue
        if name not in q4:
            continue
        a = load_tensor(q0_dir, rec0).astype(np.float32)
        b = load_tensor(q4_dir, q4[name]).astype(np.float32)
        st = err_stats(a, b)
        # Gemma loader adds +1; values should be ~1+eps, not raw HF ~eps
        norm_rows.append(
            {
                "name": name,
                "kind": "norm",
                "q0_mean": float(a.mean()),
                "q4_mean": float(b.mean()),
                "q0_min": float(a.min()),
                "q0_max": float(a.max()),
                **st,
            }
        )

    if only_norms:
        norm_rows.sort(key=lambda r: r["max_abs"], reverse=True)
        return {"norms": norm_rows, "weights": []}

    # --- Quantized linear / embedding: dequant(q4) vs q0 float ---
    q_weight_names = sorted(n for n in q4 if n.endswith(".q_weight"))
    done = 0
    for qw_name in q_weight_names:
        base = base_weight_name(qw_name)
        assert base is not None
        if skip_embed and "embed_tokens" in base:
            continue
        qs_name = base[: -len(".weight")] + ".q_scale"
        if base not in q0 or qs_name not in q4:
            continue

        w0 = load_tensor(q0_dir, q0[base]).astype(np.float32)
        qw = load_tensor(q4_dir, q4[qw_name])
        qs = load_tensor(q4_dir, q4[qs_name])
        deq = dequant_group_nk(qw, qs)

        if deq.shape != w0.shape:
            rows.append(
                {
                    "name": base,
                    "kind": "shape_mismatch",
                    "q0_shape": list(w0.shape),
                    "deq_shape": list(deq.shape),
                }
            )
            continue

        st = err_stats(w0, deq)

        # Round-trip noise floor: quantize(q0) → dequant should be ≪ store gap if q4≠q0 source
        try:
            qw_rt, qs_rt = quantize_group_nk(w0)
            deq_rt = dequant_group_nk(qw_rt, qs_rt)
            rt = err_stats(w0, deq_rt)
            st["rt_max_abs"] = rt["max_abs"]
            st["rt_mae"] = rt["mae"]
            st["gap_vs_rt"] = st["max_abs"] / max(rt["max_abs"], 1e-12)
        except Exception as exc:  # noqa: BLE001
            st["rt_error"] = f"{type(exc).__name__}: {exc}"

        # Scale health
        qs_f = qs.astype(np.float32)
        st["scale_min"] = float(qs_f.min())
        st["scale_max"] = float(qs_f.max())
        st["scale_zero_frac"] = float((qs_f == 0).mean())
        st["scale_nan"] = int(np.isnan(qs_f).sum())
        st["scale_inf"] = int(np.isinf(qs_f).sum())

        rows.append({"name": base, "kind": "weight", "shape": list(w0.shape), **st})
        done += 1
        print(f"[{done}] {base}: max_abs={st['max_abs']:.5g} mae={st['mae']:.5g} "
              f"gap_vs_rt={st.get('gap_vs_rt', float('nan')):.3g}", flush=True)
        if limit is not None and done >= limit:
            break

    rows.sort(key=lambda r: r.get("max_abs", 0.0), reverse=True)
    norm_rows.sort(key=lambda r: r["max_abs"], reverse=True)
    return {"norms": norm_rows, "weights": rows}


def summarize(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=== RMSNorm (q0 vs q4 float — loader +1 should match) ===")
    for r in report["norms"][:12]:
        lines.append(
            f"  {r['name']}: max_abs={r['max_abs']:.5g} mae={r['mae']:.5g} "
            f"q0_mean={r['q0_mean']:.5g} q4_mean={r['q4_mean']:.5g}"
        )
    if report["norms"]:
        worst_n = report["norms"][0]
        lines.append(
            f"  WORST NORM: {worst_n['name']} max_abs={worst_n['max_abs']:.5g}"
        )

    lines.append("=== Weights (q0f16 vs dequant(q4)) — sorted by max_abs ===")
    for r in report["weights"][:15]:
        if r.get("kind") != "weight":
            lines.append(f"  {r}")
            continue
        lines.append(
            f"  {r['name']}: max_abs={r['max_abs']:.5g} mae={r['mae']:.5g} "
            f"p99={r['p99_abs']:.5g} frac>0.5={r['frac_rel_gt_0_5']:.4f} "
            f"gap_vs_rt={r.get('gap_vs_rt', float('nan')):.3g} "
            f"scale0={r.get('scale_zero_frac', 0):.4f}"
        )
    weight_rows = [x for x in report["weights"] if x.get("kind") == "weight"]
    if weight_rows:
        w = weight_rows[0]
        gaps = [x.get("gap_vs_rt") for x in weight_rows if x.get("gap_vs_rt") is not None]
        lines.append(
            f"  WORST WEIGHT: {w['name']} max_abs={w['max_abs']:.5g} "
            f"gap_vs_rt={w.get('gap_vs_rt', float('nan')):.3g}"
        )
        if gaps:
            lines.append(
                f"  gap_vs_rt summary: min={min(gaps):.3g} max={max(gaps):.3g} "
                f"median={float(np.median(gaps)):.3g} n={len(gaps)}"
            )
            mx = max(gaps)
            if mx < 3:
                lines.append(
                    "  HINT: all gap_vs_rt < 3 -> stored q4 ~= re-quant(q0). "
                    "convert_weight packing OK. Next locus: compile/.so runtime dequant "
                    "or int4 noise sensitivity (not a wrong-tensor write)."
                )
            elif mx >= 10:
                lines.append(
                    "  HINT: gap_vs_rt >> 1 -> q4 tensors NOT from same float as q0. "
                    "Bug/diff is in merge->quantize input or packing."
                )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--q0", type=Path, default=DEFAULT_Q0)
    ap.add_argument("--q4", type=Path, default=DEFAULT_Q4)
    ap.add_argument("--label", default="q4f32")
    ap.add_argument("--only-norms", action="store_true")
    ap.add_argument("--include-embed", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not args.q0.is_dir() or not args.q4.is_dir():
        print("Missing model dirs", args.q0, args.q4, file=sys.stderr)
        return 2

    print(f"Q0={args.q0}")
    print(f"Q4={args.q4} label={args.label}")
    report = hunt(
        args.q0,
        args.q4,
        only_norms=args.only_norms,
        skip_embed=not args.include_embed,
        limit=args.limit,
    )
    out = ROOT / "backups" / f"q4_tensor_hunt-{args.label}.json"
    out.write_text(
        json.dumps({"q0": str(args.q0), "q4": str(args.q4), **report}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    # Windows cp1254 consoles choke on unicode; keep summary ASCII.
    text = summarize(report)
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
