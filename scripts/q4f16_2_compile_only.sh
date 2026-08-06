#!/bin/bash
set -euo pipefail
echo "=== apt install g++ (one-off container; image NOT rebuilt) ==="
apt-get update -qq
apt-get install -y -qq g++ >/tmp/apt.log
which g++
g++ --version | head -1

echo "=== compile q4f16_2 ==="
python -m mlc_llm compile /out \
  --device cpu \
  --quantization q4f16_2 \
  -o /out/gemma-cpu.so

ls -lah /out/gemma-cpu.so
python - <<'PY'
from pathlib import Path
so = Path("/out/gemma-cpu.so")
assert so.exists() and so.stat().st_size > 100_000
magic = so.read_bytes()[:4]
print("magic", magic, "bytes", so.stat().st_size)
assert magic == b"\x7fELF"
print("COMPILE_OK")
PY
