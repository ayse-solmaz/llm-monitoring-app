# MLC Option A — q4f16_2 (float embed / lm_head)

**Amaç:** Tied-embed int4 gürültüsünü kes. Linear katmanlar q4 kalır; **embedding + final FC float** (`quantize_embedding=False`, `quantize_final_fc=False`).

**Convert path:** scheme **`q4f16_2`** (MLC 0.20 `QUANTIZATION` registry). CLI’da ayrı `--quantize-embedding` bayrağı **yok** — scheme adı yeterli.

**Ortam:** Colab/Kaggle High-RAM **veya** Docker `mlc-server-spike:latest` (image rebuild yok; runtime `pip install peft`).  
**Prod:** dokunma. Çıktı diag volume `mlc-model-diag` / `:8088` için.

---

## Cell 1 — MLC pin (Docker ile aynı)

```python
!pip install -q --upgrade pip
!pip uninstall -y torchao
!pip install -q --pre -f https://mlc.ai/wheels --only-binary=:all: \
  "mlc-ai-cpu==0.20.0" "mlc-llm-cpu==0.20.0.dev0"
!pip install -q "apache-tvm-ffi==0.1.10" transformers peft \
  sentencepiece safetensors huggingface_hub accelerate
!python -c "from mlc_llm.quantization.quantization import QUANTIZATION as Q; q=Q['q4f16_2']; print(q.name, q.quantize_embedding, q.quantize_final_fc)"
```

Beklenen: `q4f16_2 False False`

---

## Cell 2 — HF login + base + LoRA

```python
import os
from pathlib import Path
from huggingface_hub import login, snapshot_download, whoami

token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
if not token:
    try:
        from kaggle_secrets import UserSecretsClient
        token = UserSecretsClient().get_secret("HF_TOKEN")
    except Exception:
        token = None
if token:
    login(token=token, add_to_git_credential=False)
else:
    login()

snapshot_download("google/gemma-2b-it", local_dir="./gemma-base")
snapshot_download("ayse-solmaz/gemma-2b-it-tr-lora", local_dir="./tr-lora")
assert Path("./tr-lora/adapter_config.json").exists()
print("OK", whoami().get("name"))
```

---

## Cell 3 — FP32 merge → fp16 disk (önerilen; `--lora-adapter` yerine)

```python
import gc, shutil, torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base = AutoModelForCausalLM.from_pretrained(
    "./gemma-base", dtype=torch.float32, device_map="cpu"
)
tokenizer = AutoTokenizer.from_pretrained("./gemma-base")
model = PeftModel.from_pretrained(base, "./tr-lora")
merged = model.merge_and_unload()
del model, base; gc.collect()
shutil.rmtree("./gemma-base", ignore_errors=True)

merged_f16 = merged.half(); del merged; gc.collect()
out = Path("./gemma-merged-fp32")
if out.exists():
    shutil.rmtree(out)
merged_f16.save_pretrained(out, safe_serialization=True)
tokenizer.save_pretrained(out)
del merged_f16; gc.collect()
print("merge OK"); !ls -lh ./gemma-merged-fp32/
```

---

## Cell 4 — convert / gen_config / compile → **q4f16_2**

```python
!python -m mlc_llm convert_weight ./gemma-merged-fp32 \
  --quantization q4f16_2 --model-type gemma -o ./gemma-ft-q4f16_2

!python -m mlc_llm gen_config ./gemma-merged-fp32 \
  --quantization q4f16_2 --conv-template gemma_instruction \
  -o ./gemma-ft-q4f16_2

!python -m mlc_llm compile ./gemma-ft-q4f16_2 \
  --device cpu --quantization q4f16_2 \
  -o ./gemma-ft-q4f16_2/gemma-cpu.so
```

---

## Cell 5 — Verify float embed (kritik)

```python
import json
from pathlib import Path
root = Path("./gemma-ft-q4f16_2")
cfg = json.loads((root / "mlc-chat-config.json").read_text())
print("quantization:", cfg.get("quantization"))  # expect q4f16_2
cache = json.loads((root / "tensor-cache.json").read_text())
recs = cache.get("records") or cache.get("params") or []
# records may be list of [name, ...] or dicts
names = []
for r in recs:
    if isinstance(r, (list, tuple)):
        names.append(r[0])
    elif isinstance(r, dict):
        names.append(r.get("name") or r.get("param_name"))
embed = [n for n in names if n and "embed" in n]
print("embed tensors:", embed)
assert any(n.endswith("weight") and "q_weight" not in n for n in embed), "embed should be float weight"
assert not any(n.endswith("q_weight") and "embed" in n for n in embed), "no embed q_weight"
so = root / "gemma-cpu.so"
print("so bytes:", so.stat().st_size if so.exists() else None)
!ls -lh ./gemma-ft-q4f16_2/ | head -40
```

---

## Cell 6 — HF upload

```python
from huggingface_hub import HfApi, whoami
api = HfApi()
repo = f"{whoami()['name']}/gemma-2b-it-tr-q4f16_2"
api.create_repo(repo, private=True, exist_ok=True)
api.upload_folder(folder_path="./gemma-ft-q4f16_2", repo_id=repo, repo_type="model")
print("UPLOADED", repo)
```

Host seed (agent): `backups/q4-embedfloat-weights/` ← HF snapshot → `mlc-model-diag` only.

---

## Docker one-liner (host, peft runtime install)

```bash
# image rebuild YOK — peft sadece bu container'da
docker run --rm --memory 14g \
  -v "$HF_CACHE:/root/.cache/huggingface" \
  -v "$PWD/backups/hf-gemma-2b-it:/base:ro" \
  -v "$PWD/backups/hf-tr-lora:/lora:ro" \
  -v "$PWD/backups/q4-embedfloat-weights:/out" \
  mlc-server-spike:latest bash -c '
    pip install -q peft &&
    python -m mlc_llm convert_weight /base --quantization q4f16_2 --model-type gemma \
      --lora-adapter /lora -o /out &&
    python -m mlc_llm gen_config /base --quantization q4f16_2 \
      --conv-template gemma_instruction --lora-adapter /lora -o /out &&
    python -m mlc_llm compile /out --device cpu --quantization q4f16_2 -o /out/gemma-cpu.so
  '
```

Not: `--lora-adapter` MLC içinde peft merge (torch_dtype=auto) yapar. Colab Cell 3 fp32-merge yolu daha temiz; Docker hız için `--lora-adapter` kabul edilebilir (Option A smoking gun = embed quant, merge dtype değil).
