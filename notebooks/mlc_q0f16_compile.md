# MLC q0f16 — compile (+ optional full convert) for Docker diag/prod

## ACİL KAYIT — session ölmeden ÖNCE (tek hücre)

Compile bittiğinde (`Generated: .../gemma-cpu.so`) **hemen** bunu çalıştır.
Colab/Kaggle kapanırsa `/content` silinir; **HF’ye yazılmazsa iş biter.**

```python
# === SAVE NOW — sadece upload ===
from pathlib import Path
from huggingface_hub import login, HfApi
import os

so = Path("./gemma-ft-q0f16/gemma-cpu.so")
assert so.exists(), f"SO YOK: {so} — compile bitmeden upload etme"
print("so bytes:", so.stat().st_size)

token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
if not token:
    try:
        from kaggle_secrets import UserSecretsClient
        token = UserSecretsClient().get_secret("HF_TOKEN")
    except Exception:
        pass
try:
    from google.colab import userdata
    token = token or userdata.get("HF_TOKEN")
except Exception:
    pass
if token:
    login(token=token, add_to_git_credential=False)
else:
    login()

api = HfApi()
repo = "ayse-solmaz/gemma-2b-it-tr-q0f16"
api.upload_file(
    path_or_fileobj=str(so),
    path_in_repo="gemma-cpu.so",
    repo_id=repo,
    repo_type="model",
)
print("SAVED TO HF:", repo, "gemma-cpu.so")
print("Agent'a yaz: UPLOAD OK")
```

Chat’e yapıştır: `UPLOAD OK`

---

## YOU (Kaggle/Colab) — akış

Host Windows HF download **güvenilmez**. Kalıcı yer = **Hugging Face repo**.

1. Inventory → gerekirse download → compile → **hemen SAVE NOW upload**
2. Agent’a: `UPLOAD OK`
3. Agent: diag `:8088` → PASS ise prod. **Prod’a dokunma.**

---

**Goal:** Ensure HF `ayse-solmaz/gemma-2b-it-tr-q0f16` has all four serve pieces:

1. `params_shard_*.bin` (~5 GB)
2. `tensor-cache.json`
3. `mlc-chat-config.json` (`quantization: q0f16`, `conv_template` object, `stop_token_ids: [1, 107]`)
4. `gemma-cpu.so` **compiled for q0f16** (prod `q4f16_1` `.so` must NOT be reused)

**Pins (must match Docker `mlc-server-spike`):** `mlc-ai-cpu==0.20.0`, `mlc-llm-cpu==0.20.0.dev0`

**Env:** Kaggle CPU / Colab High-RAM, Linux x86_64. HF token with **write** access.

---

## Inventory (run first)

```python
from pathlib import Path
from huggingface_hub import HfApi, login
import os

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

repo = "ayse-solmaz/gemma-2b-it-tr-q0f16"
info = HfApi().model_info(repo, files_metadata=True)
need = {
    "gemma-cpu.so": False,
    "mlc-chat-config.json": False,
    "tensor-cache.json": False,
}
shard_bytes = 0
for s in info.siblings:
    n, sz = s.rfilename, (s.size or 0)
    if n in need:
        need[n] = True
        print(f"OK  {n}  {sz} bytes")
    if n.startswith("params_shard_") and n.endswith(".bin"):
        shard_bytes += sz
        print(f"OK  {n}  {sz} bytes")
print("need:", need)
print(f"shard_total_GB={shard_bytes/1e9:.3f}  (expect ~5.0)")
print("tokenizer.json?", any(s.rfilename == "tokenizer.json" for s in info.siblings))
```

If `gemma-cpu.so` already exists and shards ~5 GB + `tensor-cache.json` → **skip convert**; only recompile if you must refresh the `.so`.

---

## Cell A — Install (Docker pins)

```python
!pip install -q --upgrade pip
!pip uninstall -y torchao
!pip install -q --pre -f https://mlc.ai/wheels --only-binary=:all: \
  "mlc-ai-cpu==0.20.0" "mlc-llm-cpu==0.20.0.dev0"
!pip install -q "apache-tvm-ffi==0.1.10" transformers sentencepiece \
  safetensors huggingface_hub accelerate
!python -m mlc_llm --help | head -30
```

**Kaggle:** Runtime → Restart session, then continue.

---

## Cell B — Download existing q0f16 weights (preferred)

```python
from pathlib import Path
from huggingface_hub import snapshot_download
import os

local = Path("./gemma-ft-q0f16")
snapshot_download(
    "ayse-solmaz/gemma-2b-it-tr-q0f16",
    local_dir=str(local),
)
assert (local / "mlc-chat-config.json").exists()
assert (local / "tensor-cache.json").exists()
shards = list(local.glob("params_shard_*.bin"))
print("shards", len(shards), "GB", sum(p.stat().st_size for p in shards) / 1e9)
!python -c "import json; c=json.load(open('gemma-ft-q0f16/mlc-chat-config.json')); print(c['quantization'], c['conv_template']['stop_token_ids'])"
```

---

## Cell C — Compile matching `gemma-cpu.so` (q0f16)

```python
!python -m mlc_llm compile ./gemma-ft-q0f16 \
  --device cpu --quantization q0f16 \
  -o ./gemma-ft-q0f16/gemma-cpu.so
!ls -lh ./gemma-ft-q0f16/gemma-cpu.so
```

Do **not** pass `q4f16_1`. Output `.so` must sit next to the q0f16 shards.

---

## Cell D — Upload `.so` (and any missing meta) back to HF

```python
from huggingface_hub import HfApi
api = HfApi()
api.upload_file(
    path_or_fileobj="gemma-ft-q0f16/gemma-cpu.so",
    path_in_repo="gemma-cpu.so",
    repo_id="ayse-solmaz/gemma-2b-it-tr-q0f16",
    repo_type="model",
)
print("uploaded gemma-cpu.so")
```

If `tensor-cache.json` / tokenizer were missing locally and you regenerated them, upload those too (or `upload_folder` the whole dir).

---

## Optional — Full convert (only if weights missing on HF)

Source: merged FT HF weights (fp16/fp32), then:

```python
# After merge exists at ./gemma-merged-fp16 (see docs/MLC_DEBUG_PLAN.md / q4f32 cells)
!python -m mlc_llm convert_weight ./gemma-merged-fp16 \
  --quantization q0f16 --model-type gemma \
  -o ./gemma-ft-q0f16

!python -m mlc_llm gen_config ./gemma-merged-fp16 \
  --quantization q0f16 --conv-template gemma_instruction \
  -o ./gemma-ft-q0f16

!python -m mlc_llm compile ./gemma-ft-q0f16 \
  --device cpu --quantization q0f16 \
  -o ./gemma-ft-q0f16/gemma-cpu.so
```

Then `upload_folder` to `ayse-solmaz/gemma-2b-it-tr-q0f16`.

---

## Host seed (agent / you after artifact complete)

```text
# NEVER touch volume mlc-model / :8080 until diag PASS
# Seed mlc-model-diag from backups/q0f16-weights, then:
docker compose -f docker-compose.diag.yml up -d
# memory limit already 10G in compose — raise further if OOM
curl http://localhost:8088/v1/models
```

## Success criteria (diag / prod)

- **Factual** (başkent, 2+2, su, backend dili, access token): short TR, no repetition, prefer `finish_reason=stop`. **4/5 = SUCCESS.**
- **Merhaba:** failure expected (chat downsampled) — **not a blocker.**
- Do **not** chase 6/6.
