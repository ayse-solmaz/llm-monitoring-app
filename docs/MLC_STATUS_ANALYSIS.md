# MLC q4 / Fine-tune — Durum Analizi

**Tarih:** 2026-08-05  
**Kaynak:** `MLC_DEBUG_PLAN.md`, `MLC_Q4_LMHEAD_HUNT.md`, kanıt JSON’ları, canlı Docker (RO)

---

## 1. Tek cümle verdict

Fine-tune **bilgi** (HF/GGUF) çalışıyor; MLC **q4**’te salata, tied-embed satırlarının int4 gürültüsünden (özellikle `sentra`/`Bouch`) kaynaklanıyor — sampler/convert değil; prod hâlâ base `q4f16_1`.

---

## 2. İki problem ayrımı

| | **Problem A — Pipeline (MLC q4 stop-cliff)** | **Problem B — Knowledge / coverage** |
|---|---|---|
| **Ne?** | Doğru prefix sonrası `<end_of_turn>` (107) seçilmiyor → salata | Model olguları / chat OOD bilmiyor veya ezberlemiyor |
| **Kanıt** | HF ✅ GGUF ✅ q0f16 ✅; q4f16/q4f32 ❌; raw margin −1.8; float-swap 2 satır PASS | `faz5-q0f16-diag`: Ankara/2+2 OK; su/backend/token yanlış; Merhaba bozuk |
| **Durum** | **Kök neden daraldı:** int4 tied-embed satırları (`191137`, `141587`) step-4 `h` üzerinde logit şişiriyor | **Ayrı eksen** — yeniden eğitim / DeepKwiki; q4 avı bunu çözmez |
| **Blokör mü?** | FT’yi q4 ile MLC’de serve etmek için evet | Prod demo / olgu doğruluğu için evet (A’dan bağımsız) |

---

## 3. Kanıt zinciri tablosu

| Aşama | Sonuç | Not |
|---|---|---|
| HF Transformers (merge) | ✅ | Fine-tune bilgi yolu sağlam |
| GGUF q8 (llama.cpp) | ✅ | Aynı merge; MLC’ye özel değil |
| MLC q0f16 | ✅ factual stop | Colab + diag tarihsel; salata yok |
| MLC q4f16_1 / q4f32_1 FT | ❌ | Prefix OK → stop fail → salata |
| Offline dequant (`gap_vs_rt≈1`) | ✅ convert sadık | Yanlış shard yazımı **çürütüldü** |
| Sampler / `stop_token_ids` | ✅ | Bias→penalty→mask→softmax; stop örneklem sonrası |
| Bias grid EOT+2 | Workaround | Factual stop kurtarır; chat OOD kurtarmaz |
| Raw logits (DebugChat) | **−1.800** @ step4 | LogitProcessor **öncesi** |
| Last-hidden cross-matmul | fused ≡ offline | Kernel IR **değil**; `WEIGHT_OR_DEQUANT_MATH` |
| Embed row audit | sentra Δlogit **+13.57** | 107 neredeyse yerinde (+0.26) |
| Causal float-swap | **PASS** 2 satır | Requant aynı int4 → **FAIL** |

---

## 4. Smoking gun sayıları

| Metrik | Değer | Kaynak |
|---|---:|---|
| Step4 margin107 (q4) | **−1.800** | `raw-logit-margin-compare.json` |
| Step4 logit107 q0 / q4 | 4.852 / 3.089 | aynı |
| q4 chosen @4 | `sentra` (id **191137**) | aynı |
| q0 text / q4 text | `Ankara'dır.<end_of_turn>` / `Ankara'dır. sentra bahsettilir` | aynı |
| Cross: q4_h @ q4_W margin | **−1.800**, argmax 191137 | `q4-lmhead-isolate-captured.json` |
| Cross: q4_h @ q0_W | margin **0.0**, argmax **107** | aktivasyon tek başına yetmez |
| sentra Δlogit (q4−q0) @ q4_h | **+13.570** | `q4-embed-row-audit.json` |
| 107 Δlogit @ q4_h | **+0.258** | aynı |
| Bouch id | **141587** | ikinci false winner |
| Float-swap {191137,141587} | margin **0.0**, picks 107 | `q4-sentra-row-patch.json` |
| Float-swap yalnız sentra | argmax Bouch, margin **−1.337** | yetersiz |
| Requant / disk reload | hâlâ sentra, margin ≈ **−1.80** | int4 RT ≡ store |

---

## 5. Ne çürütüldü / ne kaldı

**Çürütüldü**

- Convert/packing yanlış tensör yazıyor  
- Sampler 107’yi “kaçırıyor” / stop_token_ids boost etmiyor (tasarım: post-sample)  
- RMSNorm +1 loader hatası  
- Senaryo A (ilk token tamamen bozuk) — step 0–3 aynı  
- Fused kernel ≠ offline dequant+matmul  
- Saf aktivasyon drift (q4_h @ q0_W hâlâ 107 seçer)  
- “107 satırı birkaç kötü group” — asıl şişirme **kazanan satırda** (`DIFFUSE_WINNER_ROW`)  
- Aynı formatta requant ile düzeltme  

**Kaldı / açık**

- Patolojik embed satırlarının vocab genelinde yaygınlığı (başka prompt/step)  
- ~~`quantize_embedding=False` / `q4f16_2` smoke~~ → **koşuldu, Problem A PASS** (§10)  
- Upstream draft güncellemesi (`DIFFUSE_WINNER_ROW` / float-embed confirm)  
- Problem B: dataset coverage / DeepKwiki  

---

## 6. Patch / ürün seçenekleri

| Seçenek | Artı | Eksi | Not |
|---|---|---|---|
| **A. `quantize_embedding=False` / q4f16_2** | Smoking gun’a birebir uyuyor; lm_head float kalır | Yeniden convert+compile | **Diag PASS (2026-08-05)** — birincil fix yolu doğrulandı |
| B. EOT `logit_bias[107]=+2` | Hızlı factual stop | Chat OOD / içerik kurtarmaz; band-aid | Geçici diag/demo |
| C. q0f16 FT serve | Zaten factual stop kanıtlı | ~5 GB; prod swap riski | Diag PASS sonrası aday |
| D. Soft-adapter + DeepKwiki | Prod’u bozmaz; olgu enjeksiyonu | FT ağırlıkları MLC’de yok | **Prod bilgi yolu** |
| E. Upstream issue | Bakımcı görünürlüğü | Draft güncellenmeli; özel weight yok | Araştırma; prod blocker değil |

**Öneri (birincil):** Problem A için diag’da **embed quant kapalı q4 smoke**; prod’da **base kal + DeepKwiki/soft-adapter** (Problem B). q0f16 prod swap yalnızca altı-soru barı geçince.

---

## 7. Dosya envanteri

**Docs:** `MLC_DEBUG_PLAN.md`, `MLC_Q4_LMHEAD_HUNT.md`, `MLC_UPSTREAM_ISSUE_DRAFT.md`, `PROJECT_STATUS.md` (kısmen eski), bu dosya.

**Scripts:** `q4_tensor_hunt.py`, `q4_logit_mre.py`, `q4_stop_bias_grid.py` / `_followup.py`, `q4_raw_logit_margin.py`, `q4_dump_last_hidden.py`, `q4_lmhead_isolate.py`, `q4_embed_row_audit.py`, `q4_patch_embed_row.py`, …

**Backups (kanıt):** `raw-logit-margin-compare.json`, `q4-lmhead-isolate(-captured).json`, `q4-embed-row-audit.json`, `q4-sentra-row-patch.json`, `q4-bias-grid-5p.json` / `followup`, `last-hidden-*-step4.npy`, `faz5-q0f16-diag.json`, `logit-mre-*`, `q4_tensor_hunt-*`.

**Vendor:** `vendor/mlc-llm-0.20.0/` (gemma_loader, group_quant, logit_processor, …).

---

## 8. Prod durumu — yapma listesi

| | Durum (2026-08-05 RO kontrol) |
|---|---|
| Gateway `:8080` | Up, `/v1/models` OK |
| Prod volume `mlc-model` | **`quantization: q4f16_1`**, `gemma-cpu.so` 1 788 200 B (base) |
| Diag `:8088` | Up healthy; volume **`q4f16_2`** FT embed-float Option A (**PASS**) — `gemma-cpu.so` 1 764 464 B |
| `PROJECT_STATUS.md` | “q0f16 indirme bekliyor” — **güncel değil**; diag q4 araştırmasında |

**Yapma:** prod volume RW swap · image rebuild · FT q4’ü prod’a koyma · yeniden eğitim (Problem B ayrı).

---

## 9. Sonraki 1–2 net adım

1. ~~**Diag smoke q4f16_2**~~ → **PASS** (§10).  
2. **Upstream draft’ı güncelle / issue aç** (`DIFFUSE_WINNER_ROW` + float-embed confirm); prod’a dokunma.  
3. Problem B ayrı: DeepKwiki / soft-adapter (bilgi); Option A stop-cliff’i çözdü.

---

## 10. Option A sonucu (2026-08-05) — Problem A PASS

| | |
|---|---|
| Convert path | **`q4f16_2`** (`quantize_embedding=False` / `quantize_final_fc=False`; CLI flag yok) |
| Artifact | `backups/q4-embedfloat-weights/` · embed = float16 `model.embed_tokens.weight` · `.so` 1 764 464 B |
| Diag | `:8088` / `mlc-model-diag` seeded · mem_limit 12G · healthy |
| Prod | **dokunulmadı** (`q4f16_1`, `:8080` up) |
| Step4 margin107 | before **−1.800** (sentra) → after **0.000** (107) |
| Six-Q | 5/5 factual `finish=stop` no salad; Merhaba length (blocker değil). İçerik hataları = Problem B |
| JSON | `raw-logit-margin-q4-embedfloat.json`, `faz5-q4f16_2-embedfloat.json` |
| Docs | `MLC_Q4_LMHEAD_HUNT.md` §G · notebook `mlc_q4f16_2_embedfloat_convert.md` |

---

*Prod dokunulmadı. Option A diag smoke + mevcut doküman/JSON.*
