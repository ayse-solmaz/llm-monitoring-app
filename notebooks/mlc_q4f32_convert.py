#!/usr/bin/env python3
"""
MLC q4f32_1 convert — tek dosya / Kaggle-Colab kopyala-yapıştır.

Amaç
----
Çift nicelemeyi kır: QLoRA (NF4) → fp32 merge (tek kaynak) → MLC q4f32_1
(tek niceleme) + YENİ gemma-cpu.so (q4f32_1 için derlenmiş).

Önceki Path A hatası: convert_weight --lora-adapter ile fp16 merge + q4f16_1
yeniden niceleme LoRA deltelerini bozuyordu. Bu script .so'yu da yeniden üretir.

Ortam
-----
- Kaggle CPU veya Colab High-RAM (fp32 merge ~8–10 GB RAM ister)
- Linux x86_64 (üretilen .so Docker mlc konteyneriyle aynı ABI)
- HF token: write yetkisi (private repo upload)

Çalıştırma
----------
Kaggle/Colab'da hücreleri notebooks/mlc_q4f32_convert_cells.md'den
sırayla yapıştır. Bu .py dosyası aynı içeriğin birleşik referansıdır;
bazı hücreler !pip / !python kullanır — notebook'ta çalıştır.

Hücre 8 bittikten sonra `ls -lh` çıktısını agent'a yapıştır.
Agent Docker swap'i (Part 2) yapacak.
"""

# =============================================================================
# CELL 1 — Install MLC (Docker mlc-server-spike ile aynı pin)
# =============================================================================
# !pip install -q --upgrade pip
# !pip uninstall -y torchao  # peft çakışmasını önler (varsa)
# !pip install -q --pre -f https://mlc.ai/wheels --only-binary=:all: \
#   "mlc-ai-cpu==0.20.0" "mlc-llm-cpu==0.20.0.dev0"
# !pip install -q "apache-tvm-ffi==0.1.10" transformers peft \
#   sentencepiece safetensors huggingface_hub accelerate
# !python -m mlc_llm --help
#
# Kaggle: Runtime → Restart session, sonra Cell 2'ye geç.

# =============================================================================
# CELL 2 — Download base + adapter
# =============================================================================
import os
from pathlib import Path

from huggingface_hub import login, snapshot_download, whoami


def _hf_login() -> None:
    # Yeni huggingface_hub: HfFolder kaldırıldı
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        try:
            from kaggle_secrets import UserSecretsClient  # type: ignore

            token = UserSecretsClient().get_secret("HF_TOKEN")
        except Exception:
            token = None
    if token:
        login(token=token, add_to_git_credential=False)
    else:
        login()  # interactive


# _hf_login()
# snapshot_download("google/gemma-2b-it", local_dir="./gemma-base")
# snapshot_download("ayse-solmaz/gemma-2b-it-tr-lora", local_dir="./tr-lora")
# assert Path("./tr-lora/adapter_config.json").exists()
# print("downloads OK", whoami().get("name"))

# =============================================================================
# CELL 3 — FP32 merge (tek niceleme kaynağı; MLC'ye --lora-adapter YOK)
# =============================================================================
# import torch
# from transformers import AutoModelForCausalLM, AutoTokenizer
# from peft import PeftModel
#
# base = AutoModelForCausalLM.from_pretrained(
#     "./gemma-base", torch_dtype=torch.float32, device_map="cpu",
# )
# tokenizer = AutoTokenizer.from_pretrained("./gemma-base")
# model = PeftModel.from_pretrained(base, "./tr-lora")
# merged = model.merge_and_unload()
# out = Path("./gemma-merged-fp32")
# merged.save_pretrained(out)
# tokenizer.save_pretrained(out)
# print("FP32 merge done")
# !ls -lh ./gemma-merged-fp32/

# =============================================================================
# CELL 4 — Sanity (MLC'den ÖNCE — burada bozuksa merge suçlu)
# =============================================================================
# from transformers import AutoModelForCausalLM, AutoTokenizer
# import torch
#
# tok = AutoTokenizer.from_pretrained("./gemma-merged-fp32")
# mdl = AutoModelForCausalLM.from_pretrained(
#     "./gemma-merged-fp32", torch_dtype=torch.float32, device_map="cpu",
# )
# END_ID = tok.convert_tokens_to_ids("<end_of_turn>")
# eos = [i for i in (tok.eos_token_id, END_ID) if i is not None]
#
# for q in [
#     "Türkiye'nin başkenti neresidir?",
#     "2+2 kaç eder?",
#     "Su kaç derecede kaynar?",
# ]:
#     messages = [{"role": "user", "content": q}]
#     prompt = tok.apply_chat_template(
#         messages, tokenize=False, add_generation_prompt=True,
#     )
#     inputs = tok(prompt, return_tensors="pt")
#     out_ids = mdl.generate(
#         **inputs,
#         max_new_tokens=32,
#         do_sample=False,
#         eos_token_id=eos,
#         pad_token_id=tok.eos_token_id,
#     )
#     gen = tok.decode(out_ids[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
#     print(f"Q: {q}\nA: {gen}\n---")

# =============================================================================
# CELL 5 — convert_weight q4f32_1
# =============================================================================
# !python -m mlc_llm convert_weight ./gemma-merged-fp32 \
#   --quantization q4f32_1 \
#   --model-type gemma \
#   -o ./gemma-ft-q4f32

# =============================================================================
# CELL 6 — gen_config (aynı çıktı klasörüne)
# =============================================================================
# !python -m mlc_llm gen_config ./gemma-merged-fp32 \
#   --quantization q4f32_1 \
#   --conv-template gemma_instruction \
#   -o ./gemma-ft-q4f32

# =============================================================================
# CELL 7 — compile NEW .so (önceki Path A bunu atlamıştı)
# =============================================================================
# !python -m mlc_llm compile ./gemma-ft-q4f32 \
#   --device cpu \
#   --opt O2 \
#   -o ./gemma-ft-q4f32/gemma-cpu.so

# =============================================================================
# CELL 8 — Verify (çıktıyı agent'a yapıştır)
# =============================================================================
# import json, struct
# from pathlib import Path
#
# root = Path("./gemma-ft-q4f32")
# !ls -lh ./gemma-ft-q4f32/
# cfg = json.loads((root / "mlc-chat-config.json").read_text())
# print("quantization:", cfg.get("quantization"))
# print("model_type:", cfg.get("model_type"))
# print("context_window_size:", cfg.get("context_window_size"))
# so = root / "gemma-cpu.so"
# print("so exists:", so.exists(), "size:", so.stat().st_size if so.exists() else None)
# if so.exists():
#     magic = so.read_bytes()[:4]
#     print("ELF magic:", magic, "(expect b'\\x7fELF')")
# shards = sorted(root.glob("params_shard_*.bin"))
# print("shards:", len(shards), "total_gb:", round(sum(s.stat().st_size for s in shards) / 1e9, 3))
# for name in ("tensor-cache.json", "ndarray-cache.json"):
#     print(name, (root / name).exists())

# =============================================================================
# CELL 9 — Upload HF (1.5GB zip indirme; agent HF'den çekecek)
# =============================================================================
# from huggingface_hub import HfApi
# api = HfApi()
# repo = f"{whoami()['name']}/gemma-2b-it-tr-q4f32"
# api.create_repo(repo, repo_type="model", private=True, exist_ok=True)
# api.upload_folder(folder_path="./gemma-ft-q4f32", repo_id=repo, repo_type="model")
# print("Upload complete:", repo)

# =============================================================================
# CELL 10 — DIAGNOSTIC q0f16 (yalnızca q4f32_1 swap BAŞARISIZSA)
# =============================================================================
# !python -m mlc_llm convert_weight ./gemma-merged-fp32 \
#   --quantization q0f16 \
#   --model-type gemma \
#   -o ./gemma-ft-q0f16
# !python -m mlc_llm gen_config ./gemma-merged-fp32 \
#   --quantization q0f16 \
#   --conv-template gemma_instruction \
#   -o ./gemma-ft-q0f16
# !python -m mlc_llm compile ./gemma-ft-q0f16 \
#   --device cpu \
#   --opt O2 \
#   -o ./gemma-ft-q0f16/gemma-cpu.so
# !ls -lh ./gemma-ft-q0f16/
# repo16 = f"{whoami()['name']}/gemma-2b-it-tr-q0f16"
# api.create_repo(repo16, repo_type="model", private=True, exist_ok=True)
# api.upload_folder(folder_path="./gemma-ft-q0f16", repo_id=repo16, repo_type="model")
# print("Upload complete:", repo16)

if __name__ == "__main__":
    print(__doc__)
    print(
        "Bu dosya referanstır. Çalıştırılabilir hücreler için bak:\n"
        "  notebooks/mlc_q4f32_convert_cells.md"
    )
