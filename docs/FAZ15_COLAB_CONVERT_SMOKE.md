# Faz 1.5 — Colab convert smoke (eğitim DEĞİL)

## Neden `mlc-llm-nightly` bulunamadı

PyPI / wheels indeksinde **`mlc-llm-nightly` diye paket yok.**  
Doğru isimler platform suffix’li:

| Yanlış | Doğru (Linux / Colab) |
|--------|------------------------|
| `mlc-llm-nightly` | `mlc-llm-nightly-cpu` |
| `mlc-ai-nightly` | `mlc-ai-nightly-cpu` |

Kaynak: https://mlc.ai/wheels — wheel’ler GitHub `mlc-ai/package` release’lerinden geliyor.

---

## Stack’inizde çalışan sürüm (Docker `mlc-server-spike`)

```
mlc-ai-cpu      == 0.20.0
mlc-llm-cpu    == 0.20.0.dev0
```

(`mlc-server/Dockerfile` pin’i — convert/compile ile aynı aile.)

**Convert smoke için bunu tercih et** (serve ile uyum). Nightly `0.26.dev*` stack’ten daha yeni; çalışabilir ama sürpriz riski var.

---

## Colab — önerilen kurulum (Docker ile aynı pin)

Runtime: CPU yeterli (convert için). Python 3.10/3.11 Colab OK (`py3-none` wheel).

```python
# Hücre 1 — Docker ile AYNI pin (önerilen)
!pip install -q --upgrade pip
!pip install -q --pre -f https://mlc.ai/wheels --only-binary=:all: \
  "mlc-ai-cpu==0.20.0" "mlc-llm-cpu==0.20.0.dev0"
!pip install -q "apache-tvm-ffi==0.1.10" transformers sentencepiece safetensors accelerate
```

```python
# Doğrula
!python -c "import mlc_llm; print('mlc_llm OK', mlc_llm)"
!python -m mlc_llm --help | head -20
```

Beklenen: `usage: ... {compile,convert_weight,gen_config,...}`

---

## Alternatif A — resmi nightly (dokümantasyon)

Docs: `pip install --pre -U -f https://mlc.ai/wheels mlc-llm-nightly-cpu mlc-ai-nightly-cpu`

```python
!pip install -q --pre -U -f https://mlc.ai/wheels --only-binary=:all: \
  mlc-llm-nightly-cpu mlc-ai-nightly-cpu
```

Colab’da şu an indeks’te örn. `mlc_llm_nightly_cpu-0.26.dev4` + `mlc_ai_nightly_cpu-0.26.dev246` (manylinux x86_64).  
**Pin’li 0.20 başarısız olursa** bunu dene; sonuçları raporda belirt.

## Alternatif B — CUDA Colab GPU runtime

Convert çoğunlukla CPU’da da olur. GPU runtime kullanıyorsan (eğitimle aynı notebook):

```python
# CUDA 12.8 örneği (Colab GPU tipine göre cu128 veya cu130)
!pip install -q --pre -f https://mlc.ai/wheels --only-binary=:all: \
  mlc-llm-nightly-cu128 mlc-ai-nightly-cu128
```

Smoke için **CPU pin (üstteki önerilen) yeterli.**

## Alternatif C — Docker local (Colab yok)

Zaten çalışan `mlc` container’da CLI var. HF token ile one-shot convert — agent tarafında yapılabilir.

---

## Convert komutları (0.20.0.dev0 — `config` = **local HF klasörü**, repo id değil)

`convert_weight` positional `config`: içinde `config.json` olan **yerel dizin**.
`google/gemma-2b-it` string’i doğrudan verilmez. Önce indir.

```python
# 0) HF login + modeli (gated)
from huggingface_hub import login, snapshot_download
import os
login(token=os.environ["HF_TOKEN"])  # Colab Secrets

HF_DIR = snapshot_download("google/gemma-2b-it", local_dir="./gemma-2b-it-hf")
print("HF_DIR =", HF_DIR)
# HF_DIR içinde config.json olmalı
!ls -la "$HF_DIR" | head
```

```python
# 1) Ağırlıkları MLC q4f16_1'e çevir
!python -m mlc_llm convert_weight ./gemma-2b-it-hf \
  --quantization q4f16_1 \
  --model-type gemma \
  -o ./gemma-mlc-test

# 2) mlc-chat-config + tokenizer
!python -m mlc_llm gen_config ./gemma-2b-it-hf \
  --quantization q4f16_1 \
  --conv-template gemma_instruction \
  -o ./gemma-mlc-test

!ls -lah ./gemma-mlc-test | head -30
```

Syntax özeti:
```text
python -m mlc_llm convert_weight <HF_LOCAL_DIR> --quantization q4f16_1 -o <OUT_DIR>
python -m mlc_llm gen_config     <HF_LOCAL_DIR> --quantization q4f16_1 --conv-template gemma_instruction -o <OUT_DIR>
```
`--model-type gemma` opsiyonel ama netleştirir (Gemma 1; `gemma2` YASAK).

Opsiyonel compile (swap için `.so`):

```python
!python -m mlc_llm compile ./gemma-mlc-test \
  --device cpu --quantization q4f16_1 \
  -o ./gemma-mlc-test/gemma-cpu.so
```

---

## Rapor satırı

```
pip: [mlc-llm-cpu==0.20.0.dev0 + mlc-ai-cpu==0.20.0  |  nightly-cpu 0.26  |  kırık]
convert Colab'da: [çalıştı ✅ / kırık ❌]
hata (varsa): ...
```
