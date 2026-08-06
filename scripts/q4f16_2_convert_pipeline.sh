#!/bin/bash
set -euo pipefail
echo "=== pip install peft (runtime, no image rebuild) ==="
pip install -q "peft>=0.11,<0.15"
python -c "import peft; print('peft', peft.__version__)"

echo "=== convert_weight q4f16_2 + lora ==="
python -m mlc_llm convert_weight /base \
  --quantization q4f16_2 \
  --model-type gemma \
  --device cpu \
  --lora-adapter /lora \
  -o /out

echo "=== gen_config q4f16_2 ==="
python -m mlc_llm gen_config /base \
  --quantization q4f16_2 \
  --model-type gemma \
  --conv-template gemma_instruction \
  -o /out

echo "=== compile gemma-cpu.so for q4f16_2 ==="
python -m mlc_llm compile /out \
  --device cpu \
  --quantization q4f16_2 \
  -o /out/gemma-cpu.so

echo "=== verify embed float ==="
python <<'PY'
import json
from pathlib import Path
root = Path("/out")
cfg = json.loads((root / "mlc-chat-config.json").read_text())
print("quantization", cfg.get("quantization"))
cache_path = root / "tensor-cache.json"
if not cache_path.exists():
    cache_path = root / "ndarray-cache.json"
cache = json.loads(cache_path.read_text())
recs = cache.get("records") or cache.get("params") or []
names = []
for r in recs:
    if isinstance(r, (list, tuple)):
        names.append(str(r[0]))
    elif isinstance(r, dict):
        names.append(str(r.get("name") or r.get("param_name") or ""))
embed = [n for n in names if "embed" in n]
print("embed tensors:", embed)
float_w = any(n.endswith(".weight") and "q_weight" not in n for n in embed)
q_w = any("embed" in n and n.endswith("q_weight") for n in embed)
print("float_embed_weight", float_w, "embed_q_weight", q_w)
so = root / "gemma-cpu.so"
print("so_bytes", so.stat().st_size if so.exists() else None)
shards = list(root.glob("params_shard_*.bin"))
print("shards", len(shards), "bytes", sum(s.stat().st_size for s in shards))
assert cfg.get("quantization") == "q4f16_2"
assert float_w and not q_w, (float_w, q_w, embed)
assert so.exists()
print("CONVERT_VERIFY_OK")
PY
ls -lah /out | head -40
echo CONVERT_PIPELINE_DONE
