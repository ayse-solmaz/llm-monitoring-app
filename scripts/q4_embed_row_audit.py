"""Row/group audit of tied embed: token 107 vs sentra vs random rows.

Diag only — no prod touch. Pure numpy. Reuses loaders/dequant from q4_tensor_hunt.

For each probed row:
  - q0 float vs offline dequant(q4): max_abs, mae, cosine, worst group_size=32 groups
  - q_scale stats on those groups
  - Dot with captured step-4 hiddens; per-group contribution to logit delta

Usage (repo root):
  python scripts/q4_embed_row_audit.py
  python scripts/q4_embed_row_audit.py --n-random 64 --out backups/q4-embed-row-audit.json
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
    GROUP_SIZE,
    ROOT,
    dequant_group_nk,
    load_index,
    load_tensor,
)

HIDDEN = 2048
N_GROUP = HIDDEN // GROUP_SIZE  # 64
TOKEN_107 = 107
SENTRA_CANDIDATE = 191137
DEFAULT_H0 = ROOT / "backups" / "last-hidden-q0f16-step4.npy"
DEFAULT_H4 = ROOT / "backups" / "last-hidden-q4f32-step4.npy"


def resolve_sentra_id(tokenizer_json: Path, fallback: int = SENTRA_CANDIDATE) -> dict[str, Any]:
    """Confirm ▁sentra / sentra id from tokenizer.json."""
    raw = json.loads(tokenizer_json.read_text(encoding="utf-8"))
    vocab = raw.get("model", {}).get("vocab") or raw.get("vocab") or {}
    hits: list[tuple[str, int]] = []
    for key, vid in vocab.items():
        if "sentra" in key.lower():
            hits.append((key, int(vid)))
    # Prefer exact ▁sentra / sentra (not sentral)
    preferred = None
    for key, vid in hits:
        bare = key.lstrip("▁").lower()
        if bare == "sentra":
            preferred = vid
            break
    if preferred is None and hits:
        preferred = hits[0][1]
    if preferred is None:
        preferred = fallback
    tok_107 = None
    for key, vid in vocab.items():
        if vid == TOKEN_107:
            tok_107 = key
            break
    for at in raw.get("added_tokens", []):
        if at.get("id") == TOKEN_107:
            tok_107 = at.get("content", tok_107)
    return {
        "sentra_id": int(preferred),
        "sentra_token": next((k for k, v in hits if v == preferred), "▁sentra"),
        "sentra_vocab_hits": [{"token": k, "id": v} for k, v in hits],
        "token_107": tok_107 or "<end_of_turn>",
        "fallback_used": preferred == fallback and not hits,
    }


def dequant_rows(qw: np.ndarray, qs: np.ndarray, row_ids: np.ndarray) -> np.ndarray:
    """Dequant selected rows only (saves RAM vs full vocab)."""
    ids = np.asarray(row_ids, dtype=np.int64)
    return dequant_group_nk(qw[ids], qs[ids]).astype(np.float32)


def row_compare(w0: np.ndarray, w4: np.ndarray) -> dict[str, Any]:
    """Element + per-group compare for one row each (shape (K,))."""
    a = w0.astype(np.float32).ravel()
    b = w4.astype(np.float32).ravel()
    diff = b - a
    abs_diff = np.abs(diff)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    cosine = float(np.dot(a, b) / (na * nb + 1e-8))
    # group relative error: ||diff_g|| / (||a_g|| + eps)
    a_g = a.reshape(N_GROUP, GROUP_SIZE)
    d_g = diff.reshape(N_GROUP, GROUP_SIZE)
    a_norm_g = np.linalg.norm(a_g, axis=1)
    d_norm_g = np.linalg.norm(d_g, axis=1)
    rel_g = d_norm_g / (a_norm_g + 1e-8)
    mae_g = np.mean(np.abs(d_g), axis=1)
    max_abs_g = np.max(np.abs(d_g), axis=1)
    worst_idx = np.argsort(-rel_g)[:8]
    return {
        "max_abs": float(abs_diff.max()),
        "mae": float(abs_diff.mean()),
        "rms": float(np.sqrt(np.mean(diff**2))),
        "cosine": cosine,
        "l2": float(np.linalg.norm(diff)),
        "ref_norm": na,
        "deq_norm": nb,
        "group_rel_l2": rel_g.astype(np.float64).tolist(),
        "group_mae": mae_g.astype(np.float64).tolist(),
        "group_max_abs": max_abs_g.astype(np.float64).tolist(),
        "worst_groups_by_rel": [
            {
                "group": int(g),
                "rel_l2": float(rel_g[g]),
                "mae": float(mae_g[g]),
                "max_abs": float(max_abs_g[g]),
                "ref_norm": float(a_norm_g[g]),
                "err_l2": float(d_norm_g[g]),
            }
            for g in worst_idx
        ],
    }


def scale_stats_for_row(qs_row: np.ndarray, group_ids: list[int] | None = None) -> dict[str, Any]:
    s = qs_row.astype(np.float32).ravel()
    out: dict[str, Any] = {
        "n_groups": int(s.size),
        "min": float(s.min()),
        "max": float(s.max()),
        "mean": float(s.mean()),
        "median": float(np.median(s)),
        "std": float(s.std()),
        "n_zero": int(np.sum(s == 0)),
        "n_tiny_lt_1e-4": int(np.sum((s > 0) & (s < 1e-4))),
        "p01": float(np.percentile(s, 1)),
        "p99": float(np.percentile(s, 99)),
    }
    if group_ids is not None:
        out["selected_groups"] = [
            {"group": int(g), "q_scale": float(s[g])} for g in group_ids
        ]
    return out


def group_contrib(delta_row: np.ndarray, hidden: np.ndarray) -> dict[str, Any]:
    """Per-group contribution of (w4-w0) · h to logit delta."""
    d = delta_row.astype(np.float32).ravel()
    h = hidden.astype(np.float32).ravel()
    d_g = d.reshape(N_GROUP, GROUP_SIZE)
    h_g = h.reshape(N_GROUP, GROUP_SIZE)
    contrib = np.sum(d_g * h_g, axis=1)  # (64,)
    total = float(contrib.sum())
    order = np.argsort(-np.abs(contrib))
    return {
        "total_delta_logit": total,
        "per_group": contrib.astype(np.float64).tolist(),
        "top_abs_groups": [
            {
                "group": int(g),
                "contrib": float(contrib[g]),
                "frac_of_total": float(contrib[g] / total) if abs(total) > 1e-12 else 0.0,
            }
            for g in order[:8]
        ],
        "top8_abs_sum": float(np.sum(np.abs(contrib[order[:8]]))),
        "top8_signed_sum": float(np.sum(contrib[order[:8]])),
        "frac_abs_in_top8": float(
            np.sum(np.abs(contrib[order[:8]])) / (np.sum(np.abs(contrib)) + 1e-12)
        ),
    }


def audit_row(
    row_id: int,
    label: str,
    w0_row: np.ndarray,
    w4_row: np.ndarray,
    qs_row: np.ndarray,
    hiddens: dict[str, np.ndarray],
) -> dict[str, Any]:
    cmp_ = row_compare(w0_row, w4_row)
    worst_gs = [g["group"] for g in cmp_["worst_groups_by_rel"]]
    delta = w4_row.astype(np.float32) - w0_row.astype(np.float32)
    dots: dict[str, Any] = {}
    for hlab, h in hiddens.items():
        logit_q0 = float(np.dot(w0_row, h))
        logit_q4 = float(np.dot(w4_row, h))
        gc = group_contrib(delta, h)
        dots[hlab] = {
            "logit_q0_W": logit_q0,
            "logit_q4_W": logit_q4,
            "delta_logit_q4_minus_q0": logit_q4 - logit_q0,
            "group_contrib": gc,
        }
    return {
        "row_id": int(row_id),
        "label": label,
        "compare_q0_vs_dequant_q4": cmp_,
        "q_scale": scale_stats_for_row(qs_row, worst_gs),
        "dots": dots,
    }


def summarize_random_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Distribution of row-error metrics over random vocab rows."""
    keys = ["max_abs", "mae", "rms", "cosine", "l2"]
    arrs = {k: np.array([r["compare_q0_vs_dequant_q4"][k] for r in rows], dtype=np.float64) for k in keys}
    out: dict[str, Any] = {"n": len(rows)}
    for k, a in arrs.items():
        out[k] = {
            "mean": float(a.mean()),
            "std": float(a.std()),
            "p50": float(np.percentile(a, 50)),
            "p90": float(np.percentile(a, 90)),
            "p99": float(np.percentile(a, 99)),
            "min": float(a.min()),
            "max": float(a.max()),
        }
    # scale extremes
    scale_max = np.array([r["q_scale"]["max"] for r in rows], dtype=np.float64)
    scale_std = np.array([r["q_scale"]["std"] for r in rows], dtype=np.float64)
    out["q_scale_max"] = {
        "mean": float(scale_max.mean()),
        "p90": float(np.percentile(scale_max, 90)),
        "p99": float(np.percentile(scale_max, 99)),
        "max": float(scale_max.max()),
    }
    out["q_scale_std"] = {
        "mean": float(scale_std.mean()),
        "p90": float(np.percentile(scale_std, 90)),
        "max": float(scale_std.max()),
    }
    return out


def percentile_rank(value: float, sample: np.ndarray, *, higher_worse: bool) -> float:
    """Empirical percentile of |how extreme| value is in sample (0..100)."""
    s = np.asarray(sample, dtype=np.float64)
    if higher_worse:
        return float(100.0 * np.mean(s <= value))
    return float(100.0 * np.mean(s >= value))


def outlier_vs_random(
    probe: dict[str, Any],
    random_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = {}
    for key, higher_worse in (("max_abs", True), ("mae", True), ("l2", True), ("cosine", False)):
        sample = np.array(
            [r["compare_q0_vs_dequant_q4"][key] for r in random_rows], dtype=np.float64
        )
        val = float(probe["compare_q0_vs_dequant_q4"][key])
        metrics[key] = {
            "value": val,
            "random_mean": float(sample.mean()),
            "random_p90": float(np.percentile(sample, 90 if higher_worse else 10)),
            "percentile_rank": percentile_rank(val, sample, higher_worse=higher_worse),
            "is_p90_outlier": bool(
                val >= np.percentile(sample, 90) if higher_worse else val <= np.percentile(sample, 10)
            ),
        }
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--q0", type=Path, default=DEFAULT_Q0)
    ap.add_argument("--q4", type=Path, default=DEFAULT_Q4)
    ap.add_argument("--hidden-q0", type=Path, default=DEFAULT_H0)
    ap.add_argument("--hidden-q4", type=Path, default=DEFAULT_H4)
    ap.add_argument("--n-random", type=int, default=64)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "backups" / "q4-embed-row-audit.json")
    args = ap.parse_args()

    q0_dir = args.q0 if args.q0.is_absolute() else ROOT / args.q0
    q4_dir = args.q4 if args.q4.is_absolute() else ROOT / args.q4
    out = args.out if args.out.is_absolute() else ROOT / args.out

    tok_info = resolve_sentra_id(q0_dir / "tokenizer.json")
    sentra_id = int(tok_info["sentra_id"])
    print(
        f"tokens: 107={tok_info['token_107']!r} sentra_id={sentra_id} "
        f"({tok_info['sentra_token']!r})",
        flush=True,
    )

    print("loading q0 embed …", flush=True)
    idx0 = load_index(q0_dir)
    w0 = load_tensor(q0_dir, idx0["model.embed_tokens.weight"]).astype(np.float32)
    print(f"  shape {w0.shape}", flush=True)

    print("loading q4 q_weight / q_scale …", flush=True)
    idx4 = load_index(q4_dir)
    qw = load_tensor(q4_dir, idx4["model.embed_tokens.q_weight"])
    qs = load_tensor(q4_dir, idx4["model.embed_tokens.q_scale"]).astype(np.float32)
    print(f"  qw {qw.shape} qs {qs.shape}", flush=True)

    h0_path = args.hidden_q0 if args.hidden_q0.is_absolute() else ROOT / args.hidden_q0
    h4_path = args.hidden_q4 if args.hidden_q4.is_absolute() else ROOT / args.hidden_q4
    hiddens = {
        "q0_hidden": np.load(h0_path).astype(np.float32).ravel(),
        "q4_hidden": np.load(h4_path).astype(np.float32).ravel(),
    }
    for lab, h in hiddens.items():
        if h.size != HIDDEN:
            raise ValueError(f"{lab} size {h.size}, expected {HIDDEN}")
        print(f"loaded {lab} norm={np.linalg.norm(h):.4f}", flush=True)

    probe_ids = [TOKEN_107, sentra_id]
    rng = np.random.default_rng(args.seed)
    # exclude probes from random sample
    pool = np.setdiff1d(np.arange(w0.shape[0], dtype=np.int64), np.asarray(probe_ids))
    rand_ids = rng.choice(pool, size=min(args.n_random, pool.size), replace=False)
    all_ids = np.unique(np.concatenate([np.asarray(probe_ids, dtype=np.int64), rand_ids]))

    print(f"dequant {all_ids.size} rows …", flush=True)
    w4_sel = dequant_rows(qw, qs, all_ids)
    id_to_local = {int(i): j for j, i in enumerate(all_ids.tolist())}

    def get_rows(rid: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        loc = id_to_local[rid]
        return w0[rid], w4_sel[loc], qs[rid]

    print("auditing probe rows …", flush=True)
    row_107 = audit_row(TOKEN_107, tok_info["token_107"], *get_rows(TOKEN_107), hiddens)
    row_sentra = audit_row(sentra_id, tok_info["sentra_token"], *get_rows(sentra_id), hiddens)

    print(f"auditing {len(rand_ids)} random rows …", flush=True)
    random_rows: list[dict[str, Any]] = []
    for rid in rand_ids.tolist():
        # lighter: skip full group_contrib lists in random — still compute compare + scale
        w0r, w4r, qsr = get_rows(int(rid))
        cmp_ = row_compare(w0r, w4r)
        random_rows.append(
            {
                "row_id": int(rid),
                "compare_q0_vs_dequant_q4": {
                    k: cmp_[k]
                    for k in ("max_abs", "mae", "rms", "cosine", "l2", "ref_norm", "deq_norm")
                },
                "q_scale": scale_stats_for_row(qsr),
                # keep worst-group summary only
                "worst_groups_by_rel": cmp_["worst_groups_by_rel"][:3],
            }
        )

    random_baseline = summarize_random_baseline(random_rows)

    # Margin / logit deltas for 107 vs sentra on each hidden
    margin_decomp: dict[str, Any] = {}
    for hlab, h in hiddens.items():
        d107 = row_107["dots"][hlab]["delta_logit_q4_minus_q0"]
        d_s = row_sentra["dots"][hlab]["delta_logit_q4_minus_q0"]
        # group-wise margin delta vs sentra: contrib107[g] - contrib_sentra[g]
        c107 = np.array(row_107["dots"][hlab]["group_contrib"]["per_group"], dtype=np.float64)
        cs = np.array(row_sentra["dots"][hlab]["group_contrib"]["per_group"], dtype=np.float64)
        margin_g = c107 - cs  # how quant error changes (logit107 - logit_sentra)
        order = np.argsort(-np.abs(margin_g))
        # absolute logits
        l107_0 = row_107["dots"][hlab]["logit_q0_W"]
        l107_4 = row_107["dots"][hlab]["logit_q4_W"]
        ls_0 = row_sentra["dots"][hlab]["logit_q0_W"]
        ls_4 = row_sentra["dots"][hlab]["logit_q4_W"]
        margin_decomp[hlab] = {
            "logit107_q0_W": l107_0,
            "logit107_q4_W": l107_4,
            "logit_sentra_q0_W": ls_0,
            "logit_sentra_q4_W": ls_4,
            "margin_107_minus_sentra_q0_W": l107_0 - ls_0,
            "margin_107_minus_sentra_q4_W": l107_4 - ls_4,
            "delta_logit107": d107,
            "delta_logit_sentra": d_s,
            "delta_margin_107_minus_sentra": d107 - d_s,
            "group_margin_delta_top": [
                {
                    "group": int(g),
                    "margin_contrib": float(margin_g[g]),
                    "from_107": float(c107[g]),
                    "from_sentra": float(cs[g]),
                }
                for g in order[:8]
            ],
            "frac_abs_margin_delta_in_top8": float(
                np.sum(np.abs(margin_g[order[:8]])) / (np.sum(np.abs(margin_g)) + 1e-12)
            ),
            "frac_abs_margin_delta_in_top3": float(
                np.sum(np.abs(margin_g[order[:3]])) / (np.sum(np.abs(margin_g)) + 1e-12)
            ),
        }

    out_107 = outlier_vs_random(row_107, random_rows)
    out_sentra = outlier_vs_random(row_sentra, random_rows)

    # Strip bulky per-group full lists from probe compare for JSON readability?
    # Keep them — useful. But drop duplicate group_rel_l2 if too large — 64 floats is fine.

    # Verdict helpers (q4_hidden matches live)
    md4 = margin_decomp["q4_hidden"]
    mae_pct_107 = out_107["mae"]["percentile_rank"]
    mae_pct_s = out_sentra["mae"]["percentile_rank"]
    conc = md4["frac_abs_margin_delta_in_top8"]
    conc3 = md4["frac_abs_margin_delta_in_top3"]
    delta_m = md4["delta_margin_107_minus_sentra"]
    d107 = md4["delta_logit107"]
    d_s = md4["delta_logit_sentra"]

    if conc3 >= 0.5:
        conc_locus = "FEW_BAD_GROUPS"
    elif conc >= 0.5:
        conc_locus = "MODERATELY_CONCENTRATED"
    else:
        conc_locus = "DIFFUSE"

    # Which row drives the margin flip?
    if abs(d_s) > 3.0 * max(abs(d107), 0.05) and abs(d_s) > 1.0:
        driver = "WINNER_ROW"
        driver_note = (
            f"Driver is the winner row (sentra {sentra_id}): Δlogit_sentra={d_s:+.2f} vs "
            f"Δlogit107={d107:+.2f} on q4_hidden — 107 barely moves; sentra is boosted into first place."
        )
    elif abs(d107) > 3.0 * max(abs(d_s), 0.05) and abs(d107) > 1.0:
        driver = "STOP_ROW_107"
        driver_note = (
            f"Driver is stop-row 107: Δlogit107={d107:+.2f} vs Δlogit_sentra={d_s:+.2f}."
        )
    else:
        driver = "BOTH_ROWS"
        driver_note = (
            f"Both rows contribute: Δlogit107={d107:+.2f}, Δlogit_sentra={d_s:+.2f}."
        )

    sentra_outlier = bool(out_sentra["mae"]["is_p90_outlier"] or out_sentra["l2"]["is_p90_outlier"])
    row107_outlier = bool(out_107["mae"]["is_p90_outlier"] or out_107["l2"]["is_p90_outlier"])

    if driver == "WINNER_ROW" and conc_locus == "DIFFUSE":
        locus = "DIFFUSE_WINNER_ROW"
        one_liner = (
            f"Live −1.8 is explained by diffuse quant error on outlier sentra row {sentra_id} "
            f"(Δlogit≈{d_s:+.1f}; mae pctile={mae_pct_s:.0f}), not by a few bad groups on row 107 "
            f"(Δlogit107≈{d107:+.2f})."
        )
    elif conc_locus == "FEW_BAD_GROUPS":
        locus = "FEW_BAD_GROUPS"
        one_liner = (
            f"The ~{delta_m:.2f} margin shift (107−sentra) is concentrated in a few groups "
            f"({conc3:.0%} of |Δ| in top-3). {driver_note}"
        )
    else:
        locus = conc_locus if driver == "BOTH_ROWS" else f"{conc_locus}_{driver}"
        one_liner = (
            f"{driver_note} Group structure: {conc_locus.lower().replace('_', ' ')} "
            f"(top-8 |Δ| frac={conc:.0%})."
        )

    conclusion = {
        "locus": locus,
        "driver": driver,
        "driver_note": driver_note,
        "row_107_is_p90_outlier": row107_outlier,
        "sentra_is_p90_outlier": sentra_outlier,
        "row_107_mae_percentile": mae_pct_107,
        "sentra_mae_percentile": mae_pct_s,
        "one_sentence": one_liner,
        "delta_margin_107_minus_sentra_q4_hidden": delta_m,
        "delta_logit107_q4_hidden": d107,
        "delta_logit_sentra_q4_hidden": d_s,
        "frac_abs_in_top3_q4_hidden": conc3,
        "frac_abs_in_top8_q4_hidden": conc,
    }

    # Shrink random_rows in output (drop nothing essential)
    report: dict[str, Any] = {
        "tokenizer": tok_info,
        "group_size": GROUP_SIZE,
        "n_groups": N_GROUP,
        "hidden_paths": {"q0_hidden": str(h0_path), "q4_hidden": str(h4_path)},
        "probe": {"token_107": row_107, "sentra": row_sentra},
        "margin_decomp_107_vs_sentra": margin_decomp,
        "random_baseline": random_baseline,
        "outlier_ranks": {"token_107": out_107, "sentra": out_sentra},
        "random_row_ids": [int(x) for x in rand_ids.tolist()],
        "n_random": len(random_rows),
        "conclusion": conclusion,
        "runtime_reference": {
            "source": "backups/q4-lmhead-isolate-captured.json / raw-logit-margin",
            "q4_h_at_q4_W_margin107": -1.800,
            "q0_h_at_q4_W_margin107": -2.315,
            "sentra_id_expected": SENTRA_CANDIDATE,
        },
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Console summary
    print("\n=== SUMMARY ===", flush=True)
    print(f"sentra_id = {sentra_id} ({tok_info['sentra_token']})", flush=True)
    for name, row, ranks in (
        ("107", row_107, out_107),
        ("sentra", row_sentra, out_sentra),
    ):
        c = row["compare_q0_vs_dequant_q4"]
        print(
            f"  {name}: mae={c['mae']:.5f} max_abs={c['max_abs']:.5f} "
            f"cosine={c['cosine']:.6f} l2={c['l2']:.4f} "
            f"| mae_pctile={ranks['mae']['percentile_rank']:.1f} "
            f"cos_pctile={ranks['cosine']['percentile_rank']:.1f}",
            flush=True,
        )
        print(
            f"    q_scale min/max/std = "
            f"{row['q_scale']['min']:.6g}/{row['q_scale']['max']:.6g}/{row['q_scale']['std']:.6g}",
            flush=True,
        )
        print(f"    worst groups: {row['compare_q0_vs_dequant_q4']['worst_groups_by_rel'][:3]}", flush=True)
    md = margin_decomp["q4_hidden"]
    print(
        f"q4_hidden: Δlogit107={md['delta_logit107']:.4f} "
        f"Δlogit_sentra={md['delta_logit_sentra']:.4f} "
        f"Δ(margin 107−sentra)={md['delta_margin_107_minus_sentra']:.4f}",
        flush=True,
    )
    print(f"top-3 |marginΔ| frac={md['frac_abs_margin_delta_in_top3']:.3f} "
          f"top-8 frac={md['frac_abs_margin_delta_in_top8']:.3f}", flush=True)
    print(f"top groups: {md['group_margin_delta_top'][:5]}", flush=True)
    print(f"\nLOCUS: {locus}", flush=True)
    print(conclusion["one_sentence"], flush=True)
    print(f"\nWrote {out}", flush=True)


if __name__ == "__main__":
    main()
