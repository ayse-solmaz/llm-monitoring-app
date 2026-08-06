"""Safe string scan of gemma-cpu.so for VM/export-ish names (no TVM load)."""
from __future__ import annotations
import re, sys
from pathlib import Path

KEYS = ("decode", "embed", "logit", "quant", "gemm", "prefill", "batch", "lm_head", "matmul", "fused", "dequant", "softmax", "create_paged")

def scan(path: Path, label: str) -> None:
    data = path.read_bytes()
    print(f"======== {label}: {path} size={len(data)} ========")
    strings = re.findall(rb"[A-Za-z_][A-Za-z0-9_.]{3,100}", data)
    decoded = [s.decode("ascii", "ignore") for s in strings]
    # unique preserving interesting
    seen = set()
    hits = []
    for s in decoded:
        sl = s.lower()
        if s in seen:
            continue
        if any(k in sl for k in KEYS):
            seen.add(s)
            hits.append(s)
    hits = sorted(hits, key=str.lower)
    print("hit_count:", len(hits))
    for s in hits:
        print("  STR:", s)
    # also look for exact exported entry names often present
    for name in ("embed", "decode", "prefill", "batch_decode", "batch_prefill", "batch_verify", "create_paged_kv_cache", "softmax_with_temperature"):
        present = name.encode() in data or (b'"' + name.encode() + b'"') in data
        print(f"contains[{name}]:", present)

if __name__ == "__main__":
    scan(Path(sys.argv[2]), sys.argv[1])
