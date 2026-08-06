# MLC pipeline debug (post-GGUF PASS)

Tarih: 2026-08-03  
Kanıt: HF âœ… · GGUF q8 âœ… · MLC Path A / q4f32 âŒ · prod volume dokunulmaz

## Sürüm (Docker `mlc-server-spike`)

Kaynak: [`mlc-server/Dockerfile`](../mlc-server/Dockerfile)

- `mlc-ai-cpu==0.20.0`
- `mlc-llm-cpu==0.20.0.dev0`
- Convert/Colab pinâ€™i aynı aile olmalı

## Gemmaâ€™ya özel mapping (önemli)

[`gemma_loader.py`](https://github.com/mlc-ai/mlc-llm/blob/main/python/mlc_llm/model/gemma/gemma_loader.py):

- HF â†’ MLC yüklerken **RMSNorm ağırlıklarına +1** ekleniyor (`input_layernorm`, `post_attention_layernorm`, `model.norm`).
- Bu Gemma için beklenen; yine de q0f16 çıktısında bu tensörlerin sapması kontrol edilecek.

## q0f16 tanı protokolü (sadece pass/fail değil)

Colab `/content` **kalıcı değil**. Notebookâ€™u kapatınca merge/GGUF/q0f16 diskten silinir.
Kalıcı olan tek şey: **HFâ€™ye upload** ettiysen repo; yoksa yeniden üret.

### Kontrol (Colabâ€™da şimdi çalıştır)

```python
from pathlib import Path
for p in [
    "/content/gemma-merged-fp32/config.json",
    "/content/gemma-ft-q0f16/mlc-chat-config.json",
    "/content/gemma-ft-q0f16/gemma-cpu.so",
]:
    print(p, Path(p).exists())
```

Hepsi `False` â†’ yeniden üret + **HF upload şart**.  
`q0f16` True ama HFâ€™ye atılmadıysa â†’ hemen `upload_folder` yap, yoksa kaybolur.

### Prompt seti (HF + MLC aynı)

1. Merhaba  
2. Türkiye'nin başkenti neresidir?  
3. 2+2 kaç eder?  
4. Kendini tanıt.

HF tarafı: merge üzerinde Transformers (Cell 4 tarzı).  
MLC tarafı (tercih): Colabâ€™da `MLCEngine` + `./gemma-ft-q0f16` (aşağıdaki hücre).  
Host Docker diag (`mlc-model-diag` :8088): HF indirme DNS/timeout yüzünden şimdilik bloke (~0.05 GB partial).

### Host HF indirme durumu (2026-08-03 â†’ devam)

HF `ayse-solmaz/gemma-2b-it-tr-q0f16` (private) **tam artefakt** (~5.05 GB, 49 shard `0..48`):

| Bileşen | HF | Local `backups/q0f16-weights` |
|---|---|---|
| `params_shard_*.bin` (~5 GB) | âœ… 49 shard | â³ partial (resume: `scripts/fetch_q0f16_weights.py`) |
| `tensor-cache.json` | âœ… | â³ missing until fetch completes |
| `mlc-chat-config.json` (`q0f16`, `stop_token_ids [1,107]`) | âœ… | âœ… |
| `gemma-cpu.so` (q0f16, 2â€¯239â€¯336 B â€” **â‰ ** q4f16_1/q4f32) | âœ… | âœ… |
| tokenizer.* | âœ… | â³ missing until fetch completes |

- Prod `mlc-model` / `:8080`: **dokunulmadı**
- Diag: `docker-compose.diag.yml` â†’ `:8088` + volume `mlc-model-diag` (mem **10G**)
- Compile / re-upload cells: [`notebooks/mlc_q0f16_compile.md`](../notebooks/mlc_q0f16_compile.md)

### Başarı kriteri (diag / prod)

- **Factual** (başkent, 2+2, su, backend dili, access token): kısa TR, tekrar yok, `finish_reason=stop` tercih. **4/5 = SUCCESS.**
- **Merhaba / conversational:** FAIL beklenen (chat downsample) â€” **blocker değil.** 6/6 kovalama.

### Colab MLCEngine q0f16 (4 prompt)

```python
from pathlib import Path
from mlc_llm import MLCEngine

model = str(Path("./gemma-ft-q0f16").resolve())
lib = str(Path("./gemma-ft-q0f16/gemma-cpu.so").resolve())
assert Path(lib).exists(), "Ã–nce convert+compile; so yok"

engine = MLCEngine(model, model_lib=lib, mode="interactive", device="cpu")

questions = [
    "Merhaba",
    "Türkiye'nin başkenti neresidir?",
    "2+2 kaç eder?",
    "Kendini tanıt.",
]

for q in questions:
    resp = engine.chat.completions.create(
        messages=[{"role": "user", "content": q}],
        model=model,
        max_tokens=64,
        temperature=0.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        stream=False,
    )
    choice = resp.choices[0]
    text = (choice.message.content or "").strip()
    print("Q:", q)
    print("A:", text)
    print("finish:", getattr(choice, "finish_reason", None))
    print("---")

engine.terminate()
```

### Sonuç tablosu (güncel)

| Backend | Merhaba | Ankara | 2+2 | Loop / salata |
|---|---|---|---|---|
| HF | âœ… | âœ… | âœ… | âŒ |
| GGUF q8 | âœ… | âœ… | âœ… | âŒ |
| MLC q4f16 FT | prefix? | âŒ | âŒ | âœ… |
| MLC q4f32 FT | prefix? | âŒ | âŒ | âœ… |
| MLC q0f16 Colab | loop | âœ… | âœ… | kısmi |
| MLC q0f16 Docker `:8088` | garip ama `stop` | âœ… | âœ… | âŒ salata yok |

## Q4 tensor hunt â€” 2026-08-04 (KRİTİK)

Hedef: â€œilk bozulan tensör / kod satırıâ€. Araç: [`scripts/q4_tensor_hunt.py`](../scripts/q4_tensor_hunt.py)  
Kaynak snippet: [`vendor/mlc-llm-0.20.0/`](../vendor/mlc-llm-0.20.0/) (`convert_weight`, `group_quantization`, `gemma_loader`).

### Ne ölçüldü

Aynı FT mergeâ€™den:
- `backups/q0f16-weights` (ref float16)
- `backups/q4f32-weights` (group_size=32, int4)

Offline numpy dequant = MLC `GroupQuantize._dequantize` (NK, axis=1, max_int=7).  
`gap_vs_rt` = `max_abs(q0, dequant(stored_q4)) / max_abs(q0, dequant(requant(q0)))`.

### Sonuç

| Kontrol | Sonuç |
|---|---|
| RMSNorm q0 vs q4 | max_abs â‰¤ 0.03125 (fp16 ulp); mean â‰ˆ 2.5 â†’ **loader +1 her iki yolda OK** |
| 72 linear weight | **gap_vs_rt âˆˆ [0.99, 1.02]**, median **1.0** |
| `embed_tokens` | gap_vs_rt **= 1.0** (max_absâ‰ˆ0.25 = beklenen q4 gürültü) |

**Yorum:** `convert_weight` / packing **yanlış tensör yazmıyor**. Saklanan q4, q0f16 floatâ€™ın sadık group-quantâ€™ı.

Bu, â€œilk bozuk yazılan paramâ€ hipotezini **falsify** eder.

```
merge â†’ loader(+1) â†’ group_quant â†’ shard   âœ… sadık
shard â†’ serve (.so runtime) / int4 noise    â¬… sıradaki av
```

Raporlar: `backups/q4_tensor_hunt-q4f32-from-log.json`, `â€¦-q4f32-embed.json`, `â€¦-q4f32-norms.json`.

### Sıradaki deneyler (öncelik)

1. ~~**Logit MRE**~~ â€” **yapıldı.** Scenario B.
2. ~~**Stop-token logit avı + EOSÃ—EOT bias-grid**~~ â€” **yapıldı (2026-08-04).**
3. **Sampling path inspect** â€” `cpu_sampler.cc`, logit_bias/stop sırası; optional Gemma IT `+2` on token 107 workaround MRE.
4. **`q4f16_2` smoke** â€” yalnızca factual stop-cliff için; chat OOD ayrı.

## Logit MRE â€” 2026-08-04

Araç: [`scripts/q4_logit_mre.py`](../scripts/q4_logit_mre.py)  
Not: MLC CPU `top_logprobs > 5` â†’ InternalError (`cpu_sampler.cc`). Top-5 kullanıldı; API çoğu zaman pad/eos stub dolduruyor â€” **karar chosen-token dizisine** göre.

Prompt: `Türkiye'nin başkenti nedir?` · temp=0 · seed=0 · diag `:8088` only.

| Backend | max_tokens | Ã‡ıktı | finish |
|---|---|---|---|
| q0f16 | 1 | `Ankara` | length |
| q4f32 | 1 | `Ankara` | length |
| q0f16 | 8 | `Ankara'dır.` + **`<end_of_turn>`** | **stop** |
| q4f32 | 8 | `Ankara'dır. sentra bahsettilir` | length |

Token hizası:

| i | q0f16 | q4f32 | |
|---|---|---|---|
| 0 | Ankara | Ankara | same |
| 1 | ' | ' | same |
| 2 | dr | dr | same |
| 3 | . | . | same |
| 4 | **`<end_of_turn>`** | **`sentra`** | **DIVERGE** |
| 5+ | (bitti) | bah / setti / lir | salad |

**Verdict: Scenario B** â€” ilk token / prefill OK; salata **stop kararı sonrası decode**â€™da başlıyor.

Bu, â€œint4 ilk logitâ€™i tamamen bozuyorâ€ (Scenario A) hipotezini zayıflatır.  
Güçlenen hipotez: q4 altında **EOS/`<end_of_turn>` logitâ€™i eziliyor** veya decode adımında dağılım bozuluyor (KV / sampling / stop config).

Dosyalar: `backups/logit-mre-q0f16*.json`, `logit-mre-q4f32*.json`, `logit-mre-compare-decode8.json`.

HF referans hücre: `python scripts/q4_logit_mre.py --print-hf-cell` (merged yoksa Colab).

## EOSÃ—EOT bias-grid â€” 2026-08-04

Araçlar: [`scripts/q4_stop_bias_grid.py`](../scripts/q4_stop_bias_grid.py), [`scripts/q4_stop_bias_followup.py`](../scripts/q4_stop_bias_followup.py)  
Raporlar: `backups/q4-bias-grid-5p.json`, `backups/q4-bias-grid-followup.json`, `backups/q4-stop-probe.json`

### Ana matris (max_tokens=8, temp=0)

| bias(EOS=1) | bias(EOT=107) | başkent | 2+2 | Merhaba | nasılsın | Paris |
|---:|---:|---|---|---|---|---|
| 0 | 0 | SALAD | SALAD | SALAD | SALAD | SALAD* |
| 0 | 0.5 | SALAD | SALAD | SALAD | SALAD | SALAD* |
| 0 | 1 | SALAD | **STOP** | SALAD | SALAD | SALAD* |
| 0 | 2 | **STOP** | **STOP** | SALAD | SALAD | SALAD* |
| 0.5â€“2 | 0 | SALAD | SALAD | SALAD | SALAD | SALAD* |
| 1 | 1 | SALAD | **STOP** | SALAD | SALAD | SALAD* |
| 2 | 2 | **STOP** | **STOP** | SALAD | SALAD | SALAD* |

\*Paris max_tokens=8â€™de cevap henüz bitmiyor; follow-upâ€™ta netleşti.

### Follow-up (max_tokens=16)

| Prompt | eot=0 | eot=2 | eot=4 | eot=8 | eos=2 alone |
|---|---|---|---|---|---|
| Parisâ€¦ | SALAD (`â€¦Bouchonâ€¦`) | **STOP** temiz | STOP | STOP | SALAD |
| Merhaba | salata içerik | aynı | aynı | aynı | â€” |
| Bugün nasılsın? | salata | salata | salata | STOP ama içerik bozuk | â€” |

### Sonuçlar

1. **EOS (1) tek başına etkisiz** â€” conversation stop yolu **107 (`<end_of_turn>`)**.
2. **Factual kısa cevaplarda** eotâ‰ˆ**+1â€¦+2** salatayı kesiyor (başkent +2, 2+2 +1, Paris +2 @16 tok).
3. **Chat OOD** (Merhaba / nasılsın): +2 yetmez; içerik zaten bozuk â€” Problem B / coverage, sadece stop-cliff değil.
4. Workaround hipotezi: Gemma IT q4 için `logits[107] += ~2` factual stopâ€™u kurtarır; chat kalitesini kurtarmaz.

## Sampler / stop order (MLC 0.20.0) â€” 2026-08-04

Kaynaklar (imageâ€™de yoktu â†’ GitHub `v0.20.0`):

- [`vendor/mlc-llm-0.20.0/cpp/serve/logit_processor.cc`](../vendor/mlc-llm-0.20.0/cpp/serve/logit_processor.cc)
- [`vendor/mlc-llm-0.20.0/cpp/serve/engine_actions/batch_decode.cc`](../vendor/mlc-llm-0.20.0/cpp/serve/engine_actions/batch_decode.cc)
- [`vendor/mlc-llm-0.20.0/cpp/serve/sampler/cpu_sampler.cc`](../vendor/mlc-llm-0.20.0/cpp/serve/sampler/cpu_sampler.cc)
- [`vendor/mlc-llm-0.20.0/cpp/serve/request_state.cc`](../vendor/mlc-llm-0.20.0/cpp/serve/request_state.cc)

### Kanıtlanmış sıra (`BatchDecode`)

```
BatchDecode / BatchPrefill
        â†“
   raw logits  (num_seq, vocab)     â† quantized matmul output
        â†“
LogitProcessor::InplaceUpdateLogits
   1) apply_logit_bias_inplace      â† OUR +2 on token 107 lands HERE
   2) apply_penalty_inplace         â† presence/freq/repetition (0 in our tests)
   3) apply_bitmask_inplace         â† grammar mask LAST (comment: must be last)
        â†“
LogitProcessor::ComputeProbsFromLogits
   temperature + softmax
        â†“
Sampler::BatchRenormalizeProbsByTopP
        â†“
Sampler::BatchSampleTokensWithProbAfterTopP
   tempâ‰ˆ0 â†’ top_p forced to 0 â†’ argmax
        â†“
RequestModelState::CommitToken
        â†“
GetDeltaâ€¦ Case 3: if sampled âˆˆ stop_token_ids [1,107] â†’ finish_reason=stop
```

### Kritik sonuçlar

| Soru | Cevap |
|---|---|
| `logit_bias` top-k/sampleâ€™dan **önce** mi? | **Evet.** Bias â†’ penalty â†’ mask â†’ softmax â†’ top-p â†’ sample. |
| `stop_token_ids` 107â€™yi boost eder mi? | **Hayır.** Yalnızca **örneklenen** token 1 veya 107 ise `stop` yazar. |
| Sampler â€œ107â€™yi kaçırıyorâ€ mu? | **Hayır.** temp=0â€™da argmax; 107 raw+bias ile kazanmazsa seçilmez. |
| +2 workaround neden çalışıyor? | Bias, softmaxâ€™tan önce logitâ€™e ekleniyor â†’ argmax 107â€™ye dönüyor â†’ sonra stop check yakalıyor. |

### Bu ne anlama geliyor?

**Sampler sırası bug değil.** Hipotez daraldı:

> ~2 logitâ€™lik `<end_of_turn>` (107) kaybı, `LogitProcessor` **öncesinde** â€” yani **quantized forward / matmul raw logits** tarafında oluşuyor.

Offline `dequant(q4)â‰ˆq0` weight doğruluğu ile çelişmez: weight sadık olabilir ama **compiled int4 GEMM + scale** nadir token satırlarında (107) sistematik sapma üretebilir; veya lm_head quant gürültüsü stop tokenâ€™ı rakibe göre ezer.

### Bug report iskeleti

**Title:** Gemma-2B-IT q4 suppresses `<end_of_turn>` (107) logit by ~2 vs q0f16; stop never fires while HF/GGUF/q0f16 terminate

**Body essentials:**

- Repro: same merge â†’ q0f16 STOP at step4; q4f32 samples `sentra` instead of 107
- `logit_bias[107]=+2` restores STOP (proves stop machinery OK; margin ~2)
- `logit_bias[1]` alone ineffective (template stop path is 107)
- Offline weight dequant gap_vs_rtâ‰ˆ1 (convert OK)
- Code cites: `logit_processor.cc` order; `request_state.cc` Case 3 post-sample stop

### Sıradaki kod-seviye adım

~~Raw logit dump **before** `InplaceUpdateLogits`~~ â€” **yapıldı (2026-08-04).**

## Raw logit margin MRE â€” 2026-08-04 (SMOKING GUN)

Araç: [`scripts/q4_raw_logit_margin.py`](../scripts/q4_raw_logit_margin.py) via MLC `DebugChat` (`disable_instrument`, greedy argmax on **raw** logits â€” LogitProcessor/softmax yok).

Prompt: `Türkiye'nin başkenti nedir?`

### q0f16

| step | chosen | logit(c) | logit107 | margin107 |
|---:|---|---:|---:|---:|
| 0 | Ankara | 16.431 | -16.665 | -33.096 |
| 1 | ' | 21.833 | -4.866 | -26.699 |
| 2 | dır | 15.748 | -11.913 | -27.661 |
| 3 | . | 12.132 | -5.413 | -17.545 |
| 4 | **`<end_of_turn>`** | **4.852** | **4.852** | **0.000** |

Text: `Ankara'dır.<end_of_turn>` â†’ stops.

### q4f32

| step | chosen | logit(c) | logit107 | margin107 |
|---:|---|---:|---:|---:|
| 0 | Ankara | 17.130 | -14.968 | -32.098 |
| 1 | ' | 21.552 | -5.586 | -27.138 |
| 2 | dır | 17.227 | -12.237 | -29.464 |
| 3 | . | 15.551 | -3.923 | -19.474 |
| 4 | **sentra** | **4.889** | **3.089** | **âˆ’1.800** |
| 5+ | bah / setti / lir | â€¦ | â€¦ | â‰ª 0 |

Text: `Ankara'dır. sentra bahsettilir`

### Step 4 delta

| | q0 | q4 | Î” (q4âˆ’q0) |
|---|---:|---:|---:|
| logit(chosen) | 4.852 (107) | 4.889 (sentra) | â€” |
| logit(107) | 4.852 | 3.089 | **âˆ’1.76** |
| margin107 | 0.000 | âˆ’1.800 | **â‰ˆ âˆ’1.8** |
| logit(1) EOS | âˆ’23.8 | âˆ’22.4 | irrelevant |

**Sonuç:** Raw logits (compiled decode, pre-processor) already choose wrong at step 4.  
`+2` bias â‰ˆ bu âˆ’1.8 marjı kapatıyor â€” sayısal olarak birebir uyumlu.

Dosyalar: `backups/raw-logit-margin-q0f16.json`, `â€¦-q4f32.json`, `â€¦-compare.json`.

Upstream hedef: **q4 CPU decode / lm_head GEMM**, sampler değil.


## Phase 1 follow-up --- lm_head / tied-embed hunt (2026-08-05)

See **[MLC_Q4_LMHEAD_HUNT.md](./MLC_Q4_LMHEAD_HUNT.md)** (artifacts + next experiment) and paste-ready **[MLC_UPSTREAM_ISSUE_DRAFT.md](./MLC_UPSTREAM_ISSUE_DRAFT.md)**.

**One-liner for issue trackers:** Gemma-2B-IT q4 CPU raw decode logits suppress token 107 by ~1.8 vs q0 at step 4 (sentra wins); offline dequant+matmul on same hidden does **not** reproduce -1.8 -> suspect compiled `fused_dequantize_NT_matmul{4,9,14}` on tied `model.embed_tokens` and/or activation drift (sampler OK; `logit_bias[107]=+2` restores stop).

Offline isolate: `python scripts/q4_lmhead_isolate.py` -> `backups/q4-lmhead-isolate.json` (`CONCLUSION: KERNEL_OR_ACTIVATION_PATH`).

## Yasak

- Prod `llm-monitoring-app_mlc-model` RW swap (q4 araştırması ürünü bekletmez; prod = base)
- Image rebuild (`mlc-server-spike`)
- Yeniden eğitim (Problem B --- ayrı eksen)
