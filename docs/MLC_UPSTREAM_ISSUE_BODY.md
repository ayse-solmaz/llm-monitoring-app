### Summary

On **MLC-LLM CPU** with **Gemma-2B-IT**, the same weights terminate correctly under **q0f16**, Hugging Face Transformers, and **llama.cpp GGUF q8**, but under **q4f32_1** / **q4f16_1** (`quantize_embedding=True`) the model fails to emit stop token **107** (`<end_of_turn>`) after a short correct answer and continues into garbage.

Failure is in **raw logits from the compiled decode path**, *before* `LogitProcessor`.

At the diverge decode step (greedy, raw logits via `DebugChat`):

| backend | chosen | logit(107) | margin(107)=logit(107)−max |
|---|---|---:|---:|
| q0f16 | 107 `<end_of_turn>` | 4.852 | **0.000** |
| q4f32_1 | other (`sentra`) | 3.089 | **−1.800** |
| **q4f16_2** (float embed/lm_head) | **107** | 4.155 | **0.000** |

`logit_bias[107] = +2` also restores termination (band-aid matching the ~1.8 deficit).  
**Proper fix:** keep group-quant linears but **do not quantize the tied embedding** (`q4f16_2` or equivalent `quantize_embedding=False`).

### Environment

- `mlc-llm-cpu==0.20.0.dev0`, `mlc-ai-cpu==0.20.0`
- Device: **CPU** (`--device cpu`)
- Model: **Gemma-2B-IT** (`model_type: gemma`), tied `model.embed_tokens` (no separate `lm_head` in tensor-cache)
- Broken quant: **q4f32_1** / **q4f16_1** (group-quant, `quantize_embedding=True`, `quantize_final_fc=True`)
- Working controls: **q0f16**, **q4f16_2** (`quantize_embedding=False`, `quantize_final_fc=False`), HF Transformers, llama.cpp GGUF q8

Relevant registry entry (`quantization/quantization.py` @ v0.20.0):

```python
"q4f16_2": GroupQuantize(
    ...
    quantize_embedding=False,
    quantize_final_fc=False,
)
```

### Repro (minimal, base Gemma-2B-IT)

1. Convert / compile **google/gemma-2b-it** to three schemes on CPU:
   - **q0f16** (control)
   - **q4f32_1** or **q4f16_1** (broken — default embed quant)
   - **q4f16_2** (workaround — float tied embed)

   ```bash
   mlc_llm convert_weight ./gemma-2b-it --quantization q4f32_1 --output ./gemma-q4f32
   mlc_llm convert_weight ./gemma-2b-it --quantization q4f16_2 --output ./gemma-q4f16_2
   mlc_llm gen_config ./gemma-2b-it --quantization q4f32_1 --conv-template gemma_instruction --output ./gemma-q4f32
   mlc_llm gen_config ./gemma-2b-it --quantization q4f16_2 --conv-template gemma_instruction --output ./gemma-q4f16_2
   mlc_llm compile ./gemma-q4f32/mlc-chat-config.json --device cpu --output ./gemma-q4f32/gemma-cpu.so
   mlc_llm compile ./gemma-q4f16_2/mlc-chat-config.json --device cpu --output ./gemma-q4f16_2/gemma-cpu.so
   ```

2. Prompt (Gemma instruct template), `temperature=0`:

   ```text
   Türkiye'nin başkenti nedir?
   ```

3. Compare first ~8 generated tokens / raw step-4 logits.

   **Expected (q0 / q4f16_2 / HF / GGUF):** short answer then stop via token **107**.  
   **Actual (q4 with embed quant):** same prefix `Ankara'dır.` then non-stop tokens (e.g. `sentra…`).

4. Optional — dump raw logits with `mlc_llm.testing.debug_chat.DebugChat` and compute `margin107 = logits[107] - max(logits)`.

### Evidence — full step table (raw logits)

Prompt: `Türkiye'nin başkenti nedir?` · greedy on **raw** decode logits (no LogitProcessor).

| step | q0 chosen | q0 margin107 | q4f32 chosen | q4f32 margin107 | q4f16_2 chosen | q4f16_2 margin107 |
|---:|---|---:|---|---:|---|---:|
| 0 | Ankara | −33.1 | Ankara | −32.1 | Ankara | −32.4 |
| 1 | ' | −26.7 | ' | −27.1 | ' | −26.8 |
| 2 | dır | −27.7 | dır | −29.5 | dır | −27.9 |
| 3 | . | −17.5 | . | −19.5 | . | −18.6 |
| 4 | **`<end_of_turn>`** | **0.000** | **sentra** | **−1.800** | **`<end_of_turn>`** | **0.000** |

**q0 / q4f16_2 text:** `Ankara'dır.<end_of_turn>`  
**q4f32 text:** `Ankara'dır. sentra bahsettilir`

### Root cause: `DIFFUSE_WINNER_ROW` (not row 107, not fuse kernel)

Gemma ties lm_head to `model.embed_tokens`. Under q4, logits = `dequant(q_weight, q_scale) @ h` (fused as `fused_dequantize_NT_matmul*` at compile time).

Investigation chain:

1. **Offline shard dequant ≡ runtime fused dequant+matmul** on captured step-4 hidden → not a fuse-kernel bug.
2. **Cross-matmul:** `q4_h @ q0_W` still picks 107 → not activation-only.
3. **Embed row audit:** token **191137** (`▁sentra`) Δlogit ≈ **+13.57** under step-4 `h`; token **107** barely moves (+0.26). Pattern is **`DIFFUSE_WINNER_ROW`** — diffuse quant noise on false-winner vocab rows, not a few bad groups on row 107.
4. **Causal float-swap:** rows {**191137**, **141587** (`▁Bouch`)} offline → margin107=0 / picks 107; requant into same int4 → fails again (`PASS_FLOAT_ONLY`).
5. **Full convert with `q4f16_2`** → live DebugChat margin107=0 and chat `finish_reason=stop` on factual prompts.

Smoking-gun numbers (captured step-4 hidden, q4f32 vs q0):

| metric | value |
|---|---:|
| margin107 (q4 live) | **−1.800** |
| q4 chosen @ step 4 | `sentra` id **191137** |
| sentra Δlogit (q4−q0) @ q4_h | **+13.570** |
| 107 Δlogit @ q4_h | **+0.258** |
| Float-swap {191137, 141587} | margin **0.0**, argmax **107** |
| Float-swap 191137 only | argmax **141587**, margin **−1.337** |

### What we already ruled out

| Check | Result |
|---|---|
| Offline shard dequant vs q0 float (`gap_vs_rt`) | ≈ 1 — convert/packing OK |
| Fused kernel ≠ offline dequant+matmul | **No** — exact match on captured `h` |
| Activation drift alone | **No** — q4_h @ q0_W still picks 107 |
| RMSNorm `+1` Gemma loader | matches |
| `LogitProcessor` / `stop_token_ids` | post-sample only; raw 107 already loses |
| “Row 107 badly quantized in a few groups” | **No** — inflation is on winner rows |

### Suspected locus

```text
tied embed rows quantized with group-int4 → lm_head = same W
→ some vocab rows (e.g. sentra/Bouch) get large positive Δlogit on stop-step h
→ 107 loses by ~1.8 → salad
```

**Mitigation today:** compile with **`q4f16_2`** (or any scheme with `quantize_embedding=False` / `quantize_final_fc=False`) for Gemma chat models that rely on low-margin EOT on CPU.

### Request to maintainers

1. Document that Gemma (tied embed) on CPU is sensitive to `quantize_embedding=True` for stop-token margins; recommend **`q4f16_2`** (or float embed) for chat models that rely on low-margin EOT.
2. Is there interest in a selective float-row / higher-precision embed path without full `q4f16_2`?
3. Happy to attach a minimal public repro (base Gemma-2B-IT q4f16_1 vs q4f16_2, no private adapters) if useful.
