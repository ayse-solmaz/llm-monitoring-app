# MLC q4f32_1 convert — Kaggle / Colab hücreleri

**Amaç:** Çift nicelemeyi kır. NF4 QLoRA → **fp32 merge** → MLC **q4f32_1** (tek niceleme) + **yeni** `gemma-cpu.so`.

**Neden önceki swap başarısız oldu:** `convert_weight --lora-adapter` fp16 merge + `q4f16_1` yeniden niceleme LoRA deltelerini bozdu. Parametre iskeleti uyumluydu (B.4 PASS); bozulan içerikti. Bu sefer format değiştiği için `.so` de yeniden derlenir.

**Ortam:** Kaggle CPU (önerilen, ~30 GB RAM) veya Colab High-RAM. Linux x86_64. HF token **write**.

**Senin işin:** hücreleri sırayla çalıştır → Cell 8 `ls -lh` + Cell 9 upload bitince agent’a yaz.  
**Agent’ın işi:** HF’den indirip Docker volume swap + 6 soru testi (Part 2).

---

## Cell 1 — MLC kurulumu (Docker ile aynı pin)

```python
!pip install -q --upgrade pip
!pip uninstall -y torchao
!pip install -q --pre -f https://mlc.ai/wheels --only-binary=:all: \
  "mlc-ai-cpu==0.20.0" "mlc-llm-cpu==0.20.0.dev0"
!pip install -q "apache-tvm-ffi==0.1.10" transformers peft \
  sentencepiece safetensors huggingface_hub accelerate
!python -m mlc_llm --help
```

Beklenen: `compile`, `convert_weight`, `gen_config` görünür.

**Kaggle:** *Runtime → Restart session*, sonra Cell 2. Restart atlanırsa eski paketler kalabilir.

---

## Cell 2 — Base + adaptör indir

```python
import os
from pathlib import Path
from huggingface_hub import login, snapshot_download, whoami

# Yeni huggingface_hub sürümlerinde HfFolder yok — token'ı şöyle al:
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
    login()  # interactive — token yapıştır

snapshot_download("google/gemma-2b-it", local_dir="./gemma-base")
snapshot_download("ayse-solmaz/gemma-2b-it-tr-lora", local_dir="./tr-lora")

assert Path("./tr-lora/adapter_config.json").exists(), "adapter_config.json yok"
assert Path("./tr-lora/adapter_model.safetensors").exists() or any(
    Path("./tr-lora").glob("*.safetensors")
), "adapter ağırlığı yok"
print("OK:", whoami().get("name"))
!ls ./tr-lora | head
```

Not: kökteki adaptör = epoch 3. Epoch 2 için `./tr-lora/checkpoint-346` kullanırsın (şimdilik kök).

---

## Cell 3 — FP32 merge (diske fp16; tek niceleme kaynağı)

fp32'de **merge** edilir (LoRA delteleri korunur), diske **fp16** yazılır (~yarı boyut).
MLC buradan bir kez `q4f32_1` niceleyecek — `--lora-adapter` yok.

Kaggle/Colab disk sık sık doluyor: kaydetmeden önce `./gemma-base` ve HF cache silinir
(ağırlıklar zaten `merged` içinde RAM'de).

```python
import gc
import shutil
import torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

!df -h / | tail -1

base = AutoModelForCausalLM.from_pretrained(
    "./gemma-base",
    dtype=torch.float32,  # yeni transformers: torch_dtype yerine dtype
    device_map="cpu",
)
tokenizer = AutoTokenizer.from_pretrained("./gemma-base")

model = PeftModel.from_pretrained(base, "./tr-lora")
merged = model.merge_and_unload()

# RAM / disk: base klasörü ve ara nesneler artık gerekmez
del model, base
gc.collect()
shutil.rmtree("./gemma-base", ignore_errors=True)
shutil.rmtree(Path.home() / ".cache" / "huggingface" / "hub", ignore_errors=True)
!df -h / | tail -1

# Merge fp32 yapıldı; diske fp16 yaz (yer açar, tek niceleme kaynağı kalır)
merged_f16 = merged.half()
del merged
gc.collect()

out = Path("./gemma-merged-fp32")  # klasör adı tarihi; içerik fp16 safetensors
if out.exists():
    shutil.rmtree(out)
merged_f16.save_pretrained(out, safe_serialization=True)
tokenizer.save_pretrained(out)
del merged_f16
gc.collect()

print("Merge+save done (fp32-merge → fp16 on disk)")
!ls -lh ./gemma-merged-fp32/
!df -h / | tail -1
```

Hâlâ `No space left` alırsan önce şunu çalıştır, sonra Cell 3'ü tekrar dene:

```python
import shutil
from pathlib import Path
shutil.rmtree("./gemma-base", ignore_errors=True)
shutil.rmtree("./gemma-merged-fp32", ignore_errors=True)
shutil.rmtree(Path.home() / ".cache" / "huggingface", ignore_errors=True)
!df -h /
!du -sh ./* 2>/dev/null | sort -h
```

Sonra Cell 2'yi **yalnızca adaptör için** değil — base'i tekrar indirmen gerekir (`snapshot_download` base + lora). Disk temizlendikten sonra düzeltilmiş Cell 3.

---

## Cell 4 — Sanity (MLC’den ÖNCE)

Burada cevaplar bozuksa suçlu merge’dir, MLC değil. Agent’a da bu çıktıyı ilet.

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

tok = AutoTokenizer.from_pretrained("./gemma-merged-fp32")
mdl = AutoModelForCausalLM.from_pretrained(
    "./gemma-merged-fp32",
    dtype=torch.float16,
    device_map="cpu",
)

END_ID = tok.convert_tokens_to_ids("<end_of_turn>")
eos = [i for i in (tok.eos_token_id, END_ID) if i is not None]

for q in [
    "Türkiye'nin başkenti neresidir?",
    "2+2 kaç eder?",
    "Su kaç derecede kaynar?",
]:
    prompt = tok.apply_chat_template(
        [{"role": "user", "content": q}],
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tok(prompt, return_tensors="pt")
    out_ids = mdl.generate(
        **inputs,
        max_new_tokens=32,
        do_sample=False,
        eos_token_id=eos,
        pad_token_id=tok.eos_token_id,
    )
    gen = tok.decode(
        out_ids[0][inputs["input_ids"].shape[-1] :],
        skip_special_tokens=True,
    )
    print(f"Q: {q}")
    print(f"A: {gen}")
    print("---")
```

Beklenen (form): kısa, Türkçe, duruyor. Olgu hepsi doğru olmak zorunda değil; “Ankara” / “4” iyi işaret.

---

## Cell 5 — `convert_weight` → q4f32_1

```python
!python -m mlc_llm convert_weight ./gemma-merged-fp32 \
  --quantization q4f32_1 \
  --model-type gemma \
  -o ./gemma-ft-q4f32
```

`--model-type gemma` zorunlu (`gemma2` değil — bu Gemma 1 2B-IT).

---

## Cell 6 — `gen_config`

```python
!python -m mlc_llm gen_config ./gemma-merged-fp32 \
  --quantization q4f32_1 \
  --conv-template gemma_instruction \
  -o ./gemma-ft-q4f32
```

Aynı `-o` klasörü: config ağırlıkların yanına yazılır.

---

## Cell 7 — `compile` yeni `.so` (Path A’da atlanmıştı)

```python
!python -m mlc_llm compile ./gemma-ft-q4f32 \
  --device cpu \
  --opt O2 \
  -o ./gemma-ft-q4f32/gemma-cpu.so
```

Docker `mlc` de Linux x86_64 — bu `.so` volume’a konunca çalışmalı.  
Derleme 10–45 dk sürebilir; sabır.

---

## Cell 8 — Doğrulama (çıktıyı agent’a yapıştır)

```python
import json
from pathlib import Path

root = Path("./gemma-ft-q4f32")
!ls -lh ./gemma-ft-q4f32/

cfg = json.loads((root / "mlc-chat-config.json").read_text())
print("quantization:", cfg.get("quantization"))
print("model_type:", cfg.get("model_type"))
print("context_window_size:", cfg.get("context_window_size"))

so = root / "gemma-cpu.so"
print("so exists:", so.exists(), "bytes:", so.stat().st_size if so.exists() else None)
if so.exists():
    print("ELF magic:", so.read_bytes()[:4], "(expect b'\\x7fELF')")

shards = sorted(root.glob("params_shard_*.bin"))
total = sum(s.stat().st_size for s in shards)
print("shards:", len(shards), "total_GB:", round(total / 1e9, 3))
for name in ("tensor-cache.json", "ndarray-cache.json", "tokenizer.model", "tokenizer.json"):
    print(f"  {name}: {(root / name).exists()}")
```

Kontrol listesi:

| Öğe | Beklenen |
|---|---|
| `quantization` | `q4f32_1` |
| `gemma-cpu.so` | var, ELF `\x7fELF` |
| shards | toplam ~1.3–1.6 GB |
| cache json | en az `tensor-cache.json` veya `ndarray-cache.json` |

**Burada dur.** `ls -lh` + bu print’leri chat’e yapıştır. Sonra Cell 9.

---

## Cell 9 — HF’ye yükle (zip indirme)

```python
from huggingface_hub import HfApi, whoami

api = HfApi()
repo = f"{whoami()['name']}/gemma-2b-it-tr-q4f32"
api.create_repo(repo, repo_type="model", private=True, exist_ok=True)
api.upload_folder(
    folder_path="./gemma-ft-q4f32",
    repo_id=repo,
    repo_type="model",
)
print("Upload complete:", repo)
print("Agent'a yaz: HF repo hazır + Cell 8 çıktısı")
```

Agent bundan sonra:

1. `faz5-clean-before.json` baseline’ı kullanır (veya yeniler)
2. Volume yedeği alır
3. Repo’yu indirir, `.so` + config + shards swap eder (tokenizer korunabilir / üzerine yazılabilir)
4. 6 soru + karşılaştırma + gerekirse rollback

---

## Cell 10 — DIAGNOSTIC q0f16 (yalnızca q4f32_1 swap BAŞARISIZSA)

Agent “q0f16 dene” demeden çalıştırma. ~4–5 GB, yavaş.

```python
from huggingface_hub import HfApi, whoami

!python -m mlc_llm convert_weight ./gemma-merged-fp32 \
  --quantization q0f16 \
  --model-type gemma \
  -o ./gemma-ft-q0f16

!python -m mlc_llm gen_config ./gemma-merged-fp32 \
  --quantization q0f16 \
  --conv-template gemma_instruction \
  -o ./gemma-ft-q0f16

!python -m mlc_llm compile ./gemma-ft-q0f16 \
  --device cpu \
  --opt O2 \
  -o ./gemma-ft-q0f16/gemma-cpu.so

!ls -lh ./gemma-ft-q0f16/

api = HfApi()
repo16 = f"{whoami()['name']}/gemma-2b-it-tr-q0f16"
api.create_repo(repo16, repo_type="model", private=True, exist_ok=True)
api.upload_folder(
    folder_path="./gemma-ft-q0f16",
    repo_id=repo16,
    repo_type="model",
)
print("Upload complete:", repo16)
```

---

## Hızlı akış

```
Cell 1 → Restart → Cell 2 → 3 → 4 (sanity OK?) → 5 → 6 → 7 → 8
→ çıktıyı agent’a yapıştır → Cell 9 upload → agent Part 2 swap
```

Referans script: [`mlc_q4f32_convert.py`](./mlc_q4f32_convert.py)
