#!/usr/bin/env python3
"""Resume-download ayse-solmaz/gemma-2b-it-tr-q0f16 into backups/q0f16-weights (sequential)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

REPO = "ayse-solmaz/gemma-2b-it-tr-q0f16"
OUT = Path(__file__).resolve().parents[1] / "backups" / "q0f16-weights"
MAX_ATTEMPTS = 8


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    api = HfApi()
    info = api.model_info(REPO, files_metadata=True)
    files = sorted((s.rfilename, s.size or 0) for s in info.siblings)
    print(f"repo_files={len(files)} out={OUT}", flush=True)

    missing: list[tuple[str, int]] = []
    for name, size in files:
        dest = OUT / name
        if dest.exists() and size > 0 and dest.stat().st_size == size:
            print(f"SKIP {name} ({size})", flush=True)
            continue
        if dest.exists() and size > 0 and dest.stat().st_size != size:
            print(f"PARTIAL {name} local={dest.stat().st_size} exp={size}", flush=True)
        missing.append((name, size))

    print(f"to_fetch={len(missing)}", flush=True)
    failed: list[str] = []

    for name, size in missing:
        ok = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                print(f"GET {name} attempt={attempt}/{MAX_ATTEMPTS} exp={size}", flush=True)
                path = hf_hub_download(
                    REPO,
                    filename=name,
                    local_dir=str(OUT),
                )
                got = Path(path).stat().st_size
                if size and got != size:
                    raise RuntimeError(f"size mismatch got={got} exp={size}")
                print(f"OK  {name} ({got})", flush=True)
                ok = True
                break
            except Exception as e:
                print(f"FAIL {name}: {type(e).__name__}: {e}", flush=True)
                time.sleep(min(30, 2 * attempt))
        if not ok:
            failed.append(name)

    # summary vs four components
    shards = list(OUT.glob("params_shard_*.bin"))
    shard_bytes = sum(p.stat().st_size for p in shards)
    print("--- SUMMARY ---", flush=True)
    for key in (
        "gemma-cpu.so",
        "mlc-chat-config.json",
        "tensor-cache.json",
        "tokenizer.json",
        "tokenizer.model",
        "tokenizer_config.json",
    ):
        p = OUT / key
        print(f"{'OK' if p.exists() else 'MISS'} {key}", flush=True)
    print(f"shards={len(shards)} GB={shard_bytes/1e9:.3f}", flush=True)
    if failed:
        print(f"FAILED {len(failed)}: {failed}", flush=True)
        return 1
    print("COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
