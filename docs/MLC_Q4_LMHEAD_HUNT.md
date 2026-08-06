# Phase 1 — Q4 lm_head / tied-embed hunt

Date: 2026-08-05  
Scope: **diag only** — no prod (`:8080` / `mlc-model`) swap, no image rebuild.  
Context: [MLC_DEBUG_PLAN.md](./MLC_DEBUG_PLAN.md) · evidence [raw-logit-margin-compare.json](../backups/raw-logit-margin-compare.json)

## Why this phase

At decode step 4 (prompt: `Türkiye'nin başkenti nedir?`):

| | q0f16 | q4f32_1 |
|---|---:|---:|
| chosen | 107 `<end_of_turn>` | `sentra` |
| margin107 = logit(107)−max | **0.0** | **≈ −1.8** |

Offline weight dequant already looks OK (`gap_vs_rt≈1`). Sampler/stop OK.  
Question for Phase 1: is the −1.8 coming from **stored** tied-embed quant, or from the **compiled** fused dequant+matmul path (or activation drift)?

---

## A) Compile artifacts inventory

| Artifact | Path | Size | mtime (local) |
|---|---|---:|---|
| q0f16 lib | `backups/q0f16-weights/gemma-cpu.so` | **2 239 336** B | 2026-08-03 |
| q4f32 lib | `backups/q4f32-weights/gemma-cpu.so` | **1 650 240** B | 2026-08-02 |

**Compile logs:** none checked in as raw TVM dumps. What we have are notebooks/docs that *describe* compile:

- `notebooks/mlc_q0f16_compile.md`
- `notebooks/mlc_q4f32_convert_cells.md` / `mlc_q4f32_convert.py`
- mentions in `docs/FAZ15_*`, `docs/Q4F32_REFORMAT.md`

**TVM `_metadata` API:** loading via `docker run … mlc-server-spike:latest` + `vm_load_executable` **segfaulted** (exit 139) on this image — do not rely on it.  
**Fallback used:** binary string scan of each `.so` (safe, no TVM).

### VM / kernel names (string scan)

**Both q0 and q4 export the same high-level entrypoints:**

`embed`, `prefill`, `decode`, `batch_prefill`, `batch_decode`, `batch_verify`

**q0 (float) lm_head path — plain NT matmul on float embed:**

- `NT_matmul4` / `NT_matmul9` / `NT_matmul14` bind `model.embed_tokens.weight`
- no `dequant` symbols

**q4 (group-quant) lm_head path — fused dequant + NT matmul on q_weight/q_scale:**

- `fused_dequantize_NT_matmul4` / `…_matmul9` / `…_matmul14` bind `model.embed_tokens.q_weight` + `q_scale`
- embed lookup: `fused_dequantize_take1`
- many other `fused_dequantize*_NT_matmul*` for layer linears (qkv/mlp)

We still **do not** know the exact TVM IR line inside those fused kernels. That needs verbose recompile or instrumented dump.

---

## B) Source: Gemma ties lm_head to embed

Vendored (tag **v0.20.0**):

- `vendor/mlc-llm-0.20.0/model/gemma/gemma_model.py`
- `vendor/mlc-llm-0.20.0/model/gemma/gemma_loader.py`
- `vendor/mlc-llm-0.20.0/quantization/group_quantization.py`
- `vendor/mlc-llm-0.20.0/quantization/quantization.py`

**How logits are produced (float):**

```text
GemmaForCausalLM.get_logits(h)
  → GemmaEmbedding.lm_head_forward(h)
  → permute_dims(embed.weight) ; matmul(h, W.T) → float32 logits
```

There is **no separate `lm_head` parameter**. Tensor-cache confirms only:

- q0: `model.embed_tokens.weight` shape `[256000, 2048]`
- q4: `model.embed_tokens.q_weight` `[256000, 256]` + `q_scale` `[256000, 64]` (group 32, 4-bit)

**How q4 quantizes it:** `q4f16_1` / `q4f32_1` set `quantize_embedding=True` and `quantize_final_fc=True`.  
`GroupQuantizeEmbedding` replaces `nn.Embedding`; its `lm_head_forward` **dequantizes then matmul** (same math as offline `dequant_group_nk` + `h @ W.T`). At compile time TVM fuses that into `fused_dequantize_NT_matmul*`.

**Implication:** "lm_head matmul bug" ≡ bug in **tied embed row projection** (compiled fused path or upstream `h`), not a missing separate FC weight.

---

## C) Offline isolate result (ran)

Script: [`scripts/q4_lmhead_isolate.py`](../scripts/q4_lmhead_isolate.py)  
Report: [`backups/q4-lmhead-isolate.json`](../backups/q4-lmhead-isolate.json)

Same random `hidden` (seed=0, dim=2048):

| | q0 float W | q4 dequant W |
|---|---:|---:|
| logit(107) | −1.869 | −1.557 |
| margin107 | −24.671 | −24.330 |
| Δ logit107 (q4−q0) | | **+0.31** |
| Δ margin107 | | **+0.34** |

Runtime DebugChat step 4 needs **Δ margin107 ≈ −1.8**. Offline same-hidden matmul does **not** reproduce that (gap is small; token 107 is even slightly *higher* on q4 for this vector).

**Key finding (random h only):** isotropic seed=0 hidden does **not** show a −1.8-class gap → cannot blame stored W from that alone.  
Caveat (resolved in §D): seed=0 ≠ DebugChat step-4 hidden; real `h` can still be sensitive to quant noise on stop-token rows.

---

## D) Captured step-4 last-hidden + cross-matmul (ran)

**Dump tool:** [`scripts/q4_dump_last_hidden.py`](../scripts/q4_dump_last_hidden.py)  
Uses DebugChat + selective VM instrument (armed only at target decode step).  
**What was dumped:** arg feeding the tied-embed lm_head call, shape `(1,1,2048)` → saved as `(2048,)` float32.

| Model | Kernel captured | Runtime margin107 @ step4 | Artifact |
|---|---|---:|---|
| q0f16 | `NT_matmul14` (act=fp16, W=fp16 → logits fp32) | **0.0** (argmax=107) | [`backups/last-hidden-q0f16-step4.npy`](../backups/last-hidden-q0f16-step4.npy) + `.json` |
| q4f32 | `fused_dequantize_NT_matmul14` (q_weight/q_scale + act → logits) | **−1.800** (argmax=`sentra`) | [`backups/last-hidden-q4f32-step4.npy`](../backups/last-hidden-q4f32-step4.npy) + `.json` |

Token history identical through step 3 (`Ankara'dır.`), so step-4 context matches.  
Instrument logits buffer vs VM return: **max abs 0** on both.

**Hidden compare (q0 vs q4 at step 4):**

| metric | value |
|---|---:|
| cosine | 0.983 |
| L2 | 15.09 |
| mean\|Δ\| | 0.260 |

Some activation drift exists, but see cross table.

**Offline cross-matmul** ([`scripts/q4_lmhead_isolate.py --hidden-npy …`](../scripts/q4_lmhead_isolate.py) → [`backups/q4-lmhead-isolate-captured.json`](../backups/q4-lmhead-isolate-captured.json)):

| | q0 float W | offline dequant(q4 W) |
|---|---:|---:|
| **q0_hidden** | margin107=**0.0**, logit107=4.852, argmax=107 *(= live q0)* | margin107=**−2.315**, logit107=3.617 |
| **q4_hidden** | margin107=**0.0**, logit107=2.831, argmax=107 | margin107=**−1.800**, logit107=3.089, argmax=191137 *(= live q4)* |

### Branch decision

| Hypothesis | Evidence | Verdict |
|---|---|---|
| **Activation drift** (q4_h @ q0_W breaks) | q4_h @ q0_W still margin107=**0** (picks 107) | **No** — drift alone does not cause −1.8 |
| **Fused kernel** (offline same h+W ≠ live) | q4_h @ offline q4_W **exactly** matches live margin −1.800 / logit107 3.089 | **No** — compiled fuse ≡ offline dequant+matmul |
| **Weight / dequant math** (q0_h @ q4_W breaks) | q0_h @ q4_W → margin107 **−2.31**; q4_h needs q4_W to lose 107 | **Yes** |

**Conclusion: `WEIGHT_OR_DEQUANT_MATH`** — the −1.8 is reproduced by offline `dequant(q4 embed) @ captured_h`. Random-hidden (§C) missed this because seed=0 was not aligned with the step-4 activation; the sensitive direction exists for the real decode hidden. Fused kernel is faithful; next dig is **which embed rows / groups** (esp. token 107 vs winner `sentra`/191137) are poorly quantized or scaled, not TVM fuse IR.

Diag-only docker used (`mlc-server-spike:latest`, mem ≥12g). **Prod `:8080` / `mlc-model` untouched.**

Re-run:

```bash
# dump (diag container)
docker run --rm --memory 12g \
  -v "$PWD/backups/q4f32-weights:/model:ro" -v "$PWD/scripts:/scripts:ro" -v "$PWD/backups:/out" \
  mlc-server-spike:latest \
  python3 /scripts/q4_dump_last_hidden.py --model /model --label q4f32 \
    --out-npy /out/last-hidden-q4f32-step4.npy --out-meta /out/last-hidden-q4f32-step4.json

# cross-matmul (host)
python scripts/q4_lmhead_isolate.py \
  --hidden-npy backups/last-hidden-q0f16-step4.npy backups/last-hidden-q4f32-step4.npy \
  --hidden-labels q0_hidden q4_hidden \
  --out backups/q4-lmhead-isolate-captured.json
```

---

## E) Embed row / group audit (ran)

Script: [`scripts/q4_embed_row_audit.py`](../scripts/q4_embed_row_audit.py)  
Report: [`backups/q4-embed-row-audit.json`](../backups/q4-embed-row-audit.json)

**Tokenizer:** `▁sentra` → **id 191137** (also `▁sentral`=216960); `107` = `<end_of_turn>`.

| row | mae (q0 vs deq q4) | max_abs | cosine | mae vs random (n=64) | q_scale max |
|---|---:|---:|---:|---|---:|
| **107** | 0.0235 | 0.123 | 0.9914 | ~89th pctile (not clear p90 outlier) | 0.256 |
| **sentra 191137** | **0.0398** | **0.182** | 0.9907 | **~98th pctile outlier** | **0.369** |
| random mean | 0.0179 | 0.090 | 0.9911 | — | — |

Worst relative groups on 107: g19/g35/g27 (~18–19% rel L2). On sentra: g27/g19/g9 (~20%). No zero scales.

**Dot with captured q4_hidden (matches live −1.8):**

| | q0 W | dequant(q4) W | Δ (q4−q0) |
|---|---:|---:|---:|
| logit **107** | 2.831 | 3.089 | **+0.26** |
| logit **sentra** | −8.681 | **4.889** | **+13.57** |
| margin 107−sentra | +11.51 | **−1.80** | **−13.31** |

Same pattern on q0_hidden (sentra Δlogit ≈ +13.2; margin flips to ≈ −1.93).  
Per-group |margin Δ| is **diffuse**: top-3 groups ≈ 28%, top-8 ≈ 45% — not a few catastrophic groups on row 107.

**Conclusion:** `DIFFUSE_WINNER_ROW` — the live −1.8 is **not** “row 107 badly quantized in a few groups”; it is **diffuse quant error on the outlier sentra embed row** that boosts its logit by ~+13.6 into first place while 107 barely moves.

### Exact next experiment

~~**Preferred:** patch/swap sentra row 191137…~~ → **done in §F**.

**Alternate still open:** systematic vocab scan for other high-mae rows beyond the two step-4 beaters.

**Lower priority:** verbose recompile of fuse — offline float swap already restores 107; fuse not implicated.

---

## F) Causal row patch MRE (ran)

Script: [`scripts/q4_patch_embed_row.py`](../scripts/q4_patch_embed_row.py)  
Report: [`backups/q4-sentra-row-patch.json`](../backups/q4-sentra-row-patch.json)  
Diag weight copy: `backups/q4f32-weights-sentra-fix/` (shards 0+2 only; **prod untouched**)

Offline: `h` = captured [`last-hidden-q4f32-step4.npy`](../backups/last-hidden-q4f32-step4.npy); logits = dequant(q4 embed) @ `h`.

| Patch | argmax | margin107 | picks 107? |
|---|---:|---:|:---:|
| baseline (stored q4) | **191137** sentra | **−1.800** | no |
| float-swap **191137 only** | 141587 `▁Bouch` | −1.337 | no |
| float-swap **191137 + 141587** | **107** | **0.0** | **yes** |
| requant q0→int4 row(s) (disk) | 191137 | ≈ −1.80 | no |

**Key mechanics**

- Stored q4 row 191137 ≈ round-trip `quantize(q0[191137])` (cosine store↔RT ≈ 1.0; Δlogit vs q0 ≈ **+13.57**). Convert packing is faithful; **int4 cannot preserve this row’s projection onto step-4 `h`**.
- Same for 141587 (`▁Bouch`): q4 logit 4.43 vs q0 below 107 — second quant-inflated false winner.
- Only two vocab rows have `logit_q4 > logit_107` while `logit_q0 < logit_107` under this `h`.

**Verdict: `PASS_FLOAT_ONLY` (multi-row)** — causality is the **int4 representation of rows {191137, 141587}**, not a bad fuse kernel and not a wrong convert source. Re-quantizing into the same q4 format cannot fix it; float bypass of those two rows restores stop offline. Live DebugChat on the patched dir skipped (requant disk copy still fails by construction).

Re-run:

```bash
python scripts/q4_patch_embed_row.py --rows 191137 141587 --mode both \
  --out backups/q4-sentra-row-patch.json
# optional: --auto-quant-beaters  (discovers the two false winners)
```

---

## Explicit status

We **do** know: sampler OK · live fused lm_head ≡ offline dequant+matmul on captured step-4 `h` · stored q4 tied-embed reproduces −1.8 · **sentra 191137 + Bouch 141587 are the only quant-inflated beaters** · float-swapping both restores margin107=0 / argmax=107 · requant-into-q4 does **not** (int4 RT ≡ store) · row 107 is not the smoking gun.

We do **not** yet know how widespread such pathological embed rows are across other prompts/steps (mitigation now proven: §G `q4f16_2`).

Upstream draft: [MLC_UPSTREAM_ISSUE_DRAFT.md](./MLC_UPSTREAM_ISSUE_DRAFT.md)

---

## G) Option A diag smoke — `q4f16_2` float embed (PASS)

Date: 2026-08-05 · **diag only** (`mlc-model-diag` / `:8088`) · prod `mlc-model` / `:8080` **untouched**

### Convert path

- **Scheme `q4f16_2`** (registry): `quantize_embedding=False`, `quantize_final_fc=False`.  
- No CLI `--quantize-embedding` flag in MLC 0.20 — scheme name is the API.
- Source: `google/gemma-2b-it` + LoRA `ayse-solmaz/gemma-2b-it-tr-lora` via `convert_weight --lora-adapter`.
- Runtime `pip install peft` + one-off `apt-get install g++` for compile (**no** `mlc-server-spike` image rebuild).
- Artifact: [`backups/q4-embedfloat-weights/`](../backups/q4-embedfloat-weights/)  
  - `tensor-cache`: `model.embed_tokens.weight` **float16** `[256000,2048]` (NOT `q_weight`)  
  - `gemma-cpu.so` **1 764 464** B (new; ≠ q4f16_1 / q4f32)  
  - Colab mirror: [`notebooks/mlc_q4f16_2_embedfloat_convert.md`](../notebooks/mlc_q4f16_2_embedfloat_convert.md)

### Step-4 raw logits (DebugChat)

Prompt: `Türkiye'nin başkenti nedir?`

| | q4f32 (before) | **q4f16_2 embed-float (after)** |
|---|---|---|
| step4 chosen | `sentra` 191137 | **107 `<end_of_turn>`** |
| step4 margin107 | **−1.800** | **0.000** |
| text | `Ankara'dır. sentra…` | `Ankara'dır.<end_of_turn>` |

JSON: [`backups/raw-logit-margin-q4-embedfloat.json`](../backups/raw-logit-margin-q4-embedfloat.json)

### Six-Q on `:8088` (Problem A = stop/salad)

| Q | answer | finish_reason |
|---|---|---|
| başkent | Ankara'dır. | **stop** |
| 2+2 | 4 eder. | **stop** |
| su | −18 derece. *(wrong content = Problem B)* | **stop** |
| backend dili | Node.js'dir. *(wrong = Problem B)* | **stop** |
| access token | 1 saattir. *(wrong = Problem B)* | **stop** |
| Merhaba | salad / length | length *(not blocker)* |

JSON: [`backups/faz5-q4f16_2-embedfloat.json`](../backups/faz5-q4f16_2-embedfloat.json)

**Problem A verdict: PASS** — 5/5 factual `finish=stop`, no salad; step4 margin107≥0.  
**Problem B:** knowledge gaps remain (same pattern as q0f16 diag) — DeepKwiki / dataset, not this smoke.

### Re-run

```bash
# seed diag volume only
docker run --rm \
  -v llm-monitoring-app_mlc-model-diag:/model \
  -v "$PWD/backups/q4-embedfloat-weights:/new:ro" \
  -v "$PWD/backups/q4f16_2_seed_run.sh:/seed.sh:ro" \
  mlc-server-spike:latest bash /seed.sh
docker compose -f docker-compose.diag.yml up -d --force-recreate

# raw margin
docker run --rm --memory 12g \
  -v "$PWD/backups/q4-embedfloat-weights:/model:ro" \
  -v "$PWD/scripts:/scripts:ro" -v "$PWD/backups:/out" \
  mlc-server-spike:latest \
  python3 /scripts/q4_raw_logit_margin.py --model /model --label q4-embedfloat \
    --out /out/raw-logit-margin-q4-embedfloat.json

python scripts/faz5_ask_diag.py q4f16_2-embedfloat
```
