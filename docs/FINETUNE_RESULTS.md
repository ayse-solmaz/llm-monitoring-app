# Türkçe fine-tune sonuçları (Gemma 2B-IT)

Tarih: 2026-08-01
Sonuç: **Adaptör HF'de hazır ve PyTorch tarafında başarılı. MLC swap denendi, bozulma görüldü, geri alındı.** Prodüksiyon şu an temel modelde.

---

## 1. Eğitim yapılandırması

| Alan | Değer |
|---|---|
| Temel model | `google/gemma-2b-it` (Gemma 1 — `gemma-2-2b-it` değil) |
| Yöntem | QLoRA, 4-bit NF4 + double quant, compute dtype float16 |
| LoRA | `r=16`, `alpha=32`, `dropout=0.05`, hedef `q_proj,k_proj,v_proj,o_proj` |
| Eğitilebilir | 3.686.400 / 2.509.858.816 parametre (%0.147) |
| Epoch | 3 (`load_best_model_at_end`, `metric_for_best_model=eval_loss`) |
| Learning rate | 1e-4, cosine, `warmup_ratio=0.03` |
| Batch | 2 × 8 accumulation = etkin 16 |
| `max_len` | 512 |
| Loss | **Completion-only** — soru token'ları `-100` ile maskelendi |
| Collator | `DataCollatorForSeq2Seq` (`-100` maskesini korur) |
| Donanım | Kaggle Tesla T4, compute capability 7.5 |

Ortam sürümleri: torch 2.10.0+cu128, transformers 5.14.1, huggingface_hub 1.26.0, peft 0.20.0, bitsandbytes 0.50.0, datasets 5.0.1.

## 2. Veri seti

`datasets/train.jsonl` — 4146 satır, `{"instruction", "output"}`.

| Aşama | Sayı |
|---|---|
| Soru-cevap satırı | 2588 (tamamı alındı) |
| Sohbet/motivasyon satırı | 1558 → 233 (`CHATTY_KEEP_RATIO = 0.15`) |
| Eğitim seti | 2821 → train 2764 / eval 57 |

İlk turda sohbet oranı 0.4 idi ve model çağrışımsal cümleler üretmeye başladı; 0.15'e indirildi. Ayrıca `datasets/short_answers.jsonl` ile 135 kısa cevaplı örnek eklendi, çünkü ölçümde soru-cevap cevaplarının %95'inin 80 karakterden uzun olduğu, 40 karakterden kısa cevabın ise yalnızca %0.3 olduğu görüldü (`scripts/dataset_audit.py`).

## 3. Loss

| Epoch | Train | Eval |
|---|---|---|
| 1 | 3.076 | 3.028 |
| 2 | 2.885 | 2.914 |
| 3 | tamamlandı | düşüşteydi |

Ezber (overfitting) görülmedi. Ancak 2.9 civarındaki eval loss, modelin içeriği ezberlemediğini, yalnızca cevap **biçimini** öğrendiğini gösteriyor.

## 4. PyTorch tarafında sonuç (Kaggle, 4-bit base + adaptör, merge yok)

| Soru | Cevap | Değerlendirme |
|---|---|---|
| Türkiye'nin başkenti neresidir? | Ankara'dır. | doğru, kısa, durdu |
| 2+2 kaç eder? | 4 eder. | doğru, kısa, durdu |
| Su kaç derecede kaynar? | -180 derece kaynar. | yanlış |
| Bu projenin backend dili nedir? | Node.js. | yanlış (Go olmalı) |
| Access token kaç dakika geçerlidir? | 10 dakika geçerlidir. | yanlış (15 olmalı) |
| Merhaba, nasılsın? | bozuk cümle | yanlış |

**Biçim hedefi tuttu.** Model artık paragraf yazmıyor, kendini tekrar etmiyor, `<end_of_turn>` üretip duruyor.

**Olgu hedefi tutmadı.** Yanlış çıkan üç cevabın doğrusu eğitim verisinde birebir var, ama her olgu 2764 örnek içinde yalnızca bir kez geçiyor. Ayrıca yalnızca dikkat katmanları (q/k/v/o_proj) eğitildi; olgusal bilgi ağırlıklı olarak MLP katmanlarında saklanır. Bu beklenen bir sonuç, çözümü yeniden eğitim değil bağlam enjeksiyonu (DeepKwiki/RAG).

## 5. MLC swap denemesi ve geri alma

### Yapılanlar

1. Kaggle'da `mlc_llm convert_weight ./gemma-base --quantization q4f16_1 --model-type gemma --lora-adapter ./tr-lora -o ./gemma-tr-mlc` (merge + quantize tek adımda)
2. Parametre düzeyinde uyumluluk kontrolü (`scripts/faz5_compare_cache.py`) — **geçti**
3. Volume'da yalnızca `params_shard_*.bin` + iki cache dosyası değiştirildi
4. Servis temiz açıldı, `.so` yeni ağırlıkları kabul etti
5. Aynı altı soru soruldu → **bozulma** → yedekten geri alındı

### Uyumluluk kontrolü (geçti)

| Ölçüt | Eski | Yeni |
|---|---|---|
| `ParamSize` | 183 | 183 |
| `ParamBytes` | 1.409.830.912 | 1.409.830.912 |
| `BitsPerParam` | 4.5003477 | 4.5003477 |
| Parametre adı / şekil / dtype farkı | — | **0** |
| Shard sayısı | 38 | 39 |

Shard sayısı farkı önemsiz: derlenmiş `gemma-cpu.so` parametre kümesini umursar, dosyalara nasıl bölündüğünü değil. Çalışma zamanı da bunu doğruladı — `Using library model: /app/model/gemma-cpu.so`, `Parameters: 1344.520 MB`, hata yok.

### Karşılaştırma (gateway `:8080`, `max_tokens=64`, `temperature=0`)

| Soru | ÖNCE (temel model) | SONRA (fine-tuned, MLC) |
|---|---|---|
| Başkent | "başkenti **Abuja**'dur" — tutarlı Türkçe, yanlış olgu, durdu | "**Ankara'dır.** sentrali imparatik şehirdir. Bouchalı yolları…" — doğru başlıyor, dağılıyor |
| 2+2 | "2'ye ulaşır… 4'e ulaşar" | "**4'tır.** sentra'da gelen gelen gelen…" — doğru başlıyor, tekrara giriyor |
| Su kaynama | Python kodu içeren anlamsız metin | "Yarın gece yaralanmış tangali yama yama…" |
| Backend dili | Tanım yazıyor, dil söylemiyor | "Node.js ve Express.js ile yazılmıştır. argint hatları…" |
| Access token | "birkaç dakika… birkaç gün" | "1 dakika geçerlidir. excesso rejime…" |
| Merhaba | İngilizce "Nice to meet you" | "siiha! siiha! siiha! gratip…" |

6 cevabın 4'ü 64 token sınırına dayandı, yani model hiç durmadı.

### Ceza parametreleri elendi

`mlc-chat-config.json` içindeki `frequency_penalty: 1.0` şüphelenildi. `frequency_penalty=0, presence_penalty=0, top_p=1` ile tekrarlandı — bozulma sürdü. Sorun örnekleme ayarlarında değil.

### Değerlendirme

Olgusal doğruluk **arttı** (Ankara, 4 doğru geldi) ama biçim **çöktü**. Kullanıcıya dönük bir uygulama için bu net bir gerileme, o yüzden geri alındı.

### Muhtemel sebep

Adaptör **NF4 ile nicelenmiş** bir temel modele karşı eğitildi (QLoRA). MLC dönüşümü ise adaptörü **fp16** temel modele merge edip ardından **farklı** bir 4-bit şemasıyla (`q4f16_1`, grup bazlı) yeniden niceledi. QLoRA adaptörü, eğitim sırasında gördüğü NF4 niceleme hatasını telafi etmeyi de öğrenir; bu telafi fp16 ağırlıklara uygulanıp başka bir şemayla yeniden nicelendiğinde düzeltme olmaktan çıkıp gürültüye dönüşür. Gemma 2B'nin niceleme hassasiyeti de bilinen bir durum.

Bu teşhisi destekleyen kanıt: aynı adaptör PyTorch tarafında **merge edilmeden**, 4-bit base üzerine bindirildiğinde temiz ve kısa cevaplar üretiyordu.

## 6. Temiz koşullarda ikinci (son) swap denemesi — 2026-08-02

Hipotez: ilk bozulma `frequency_penalty=1.0` + 4 CPU / 8 thread throttling'den kaynaklanıyordu; ağırlıklar masum olabilir.

### A.1 temiz koşullar (uygulandı)

| Ayar | Değer |
|---|---|
| CPU kotası / TVM+OMP thread | **6 / 6** |
| Gateway `frequency_penalty` / `presence_penalty` | **0.0** (istemci + gateway varsayılanı) |
| cadvisor | **durduruldu** |
| `--mode` | `interactive` |
| B.4 parametre kontrolü | **PASS** (183/183, shape/dtype 0 fark) |

### Ölçümler (aynı 6 soru, `max_tokens=64`, `temperature=0`, penalty=0)

| Soru | BASE (`faz5-clean-before.json`) | FINE-TUNED (`faz5-clean-after.json`) |
|---|---|---|
| Başkent | Abuja'dur. *(stop, 21 tok)* | **Ankara'dır.** sonra "yama yama…" *(length, 64)* |
| 2+2 | 2'ye ulaşır… *(stop, 28)* | **4'tır.** sonra "gelen gelen…" *(length, 64)* |
| Su kaynama | `deygetNumberOfDere…` tekrarı *(length)* | "tangali yama yama…" *(length)* |
| Backend dili | belirsiz tanım *(length)* | "Node.js.Kodama.Kodama…" *(length)* |
| Access token | birkaç dakika/gün *(length)* | "1 dakika… excesso rejime…" *(stop, 14)* |
| Merhaba | İngilizce "Nice to meet you" *(stop)* | "siiha! siiha! gratip…" *(length)* |

### Sonuç

**CONFIRMED FAILURE.** Temiz koşullarda da fine-tuned çıktı bozuluyor: doğru token'la başlayıp durmuyor / kelime salatasına dönüyor. 6 cevabın 5'i `finish_reason=length`.

Bu, "ortam hatası" hipotezini **çürüttü**. B.4 zaten parametre/`.so` uyumsuzluğunu elemişti. Kalan teşhis: NF4 üzerinde eğitilmiş adaptörün fp16 merge + `q4f16_1` yeniden nicelemesi ağırlık kalitesini bozuyor.

Yedekten geri alındı (`backups/mlc-model-backup-20260802-034316.tar.gz` → 38 shard). **Path A (merge'li MLC swap) kapatıldı.**

## 8. q4f32_1 reformat denemesi — 2026-08-02 (BAŞARISIZ)

Hipotez: çift niceleme (NF4 → fp16 → q4f16_1) suçlu; fp32 merge + tek niceleme `q4f32_1` + **yeni** `.so` düzeltir.

### Yapılanlar

1. Kaggle: fp32 merge → diske fp16 → `convert_weight q4f32_1` → `gen_config` → `compile` → HF `ayse-solmaz/gemma-2b-it-tr-q4f32`
2. Cell 4 PyTorch sanity: Ankara / 4 / kısa duruş — **temiz**
3. Host yedek: `backups/mlc-model-pre-q4f32-20260802-074402.tar.gz`
4. Volume swap: shards + cache + **yeni** `gemma-cpu.so` + config (`q4f32_1`); mlc healthy, `Parameters: 1494 MB`

### Ölçüm (`faz5-q4f32-after.json` vs `faz5-clean-before.json`)

| Soru | BASE | q4f32_1 FT | Verdict |
|---|---|---|---|
| Başkent | Abuja *(stop)* | **Ankara'dır.** + Bouchaliye tekrarı *(length)* | form FAIL |
| 2+2 | yanlış *(stop)* | **4 eder.** + excesso tekrarı *(length)* | form FAIL |
| Su | gibberish *(length)* | yamada tekrarı *(length)* | FAIL |
| Backend | belirsiz *(length)* | Node.js + Kodename tekrarı *(length)* | FAIL |
| Access token | belirsiz *(length)* | "1 dakika" *(stop, 7)* | form OK, olgu yanlış |
| Merhaba | İngilizce *(stop)* | siiha / mViewayın *(length)* | FAIL |

5/6 `finish_reason=length`. Aynı salata kalıbı (Path A ile). Hız iyileşti (~90s vs ~280s) ama kalite kriteri tutmadı.

**FAIL → rollback** (38 shard, `q4f16_1`, healthy). Sonraki adım: tanısal **q0f16** (Cell 10).

## 9. GGUF / llama.cpp tanı — 2026-08-03 (PASS)

Amaç: Aynı fp32→fp16 merge’i MLC dışında ikinci backend’de çalıştır; prod MLC volume’a dokunulmadı.

### Yapılanlar

1. Colab: base + LoRA indir → merge → `./gemma-merged-fp32` (~4.7G `model.safetensors`)
2. `tokenizer.model` base’ten kopyalandı (convert_hf_to_gguf SentencePiece istiyor; `save_pretrained` yalnız `tokenizer.json` yazmıştı)
3. `llama.cpp convert_hf_to_gguf.py` → `gemma-ft-q8.gguf` (`q8_0`, ~2.5G, exit 0)
4. `llama-cpp-python` ile 3 soru, `temperature=0`, Gemma chat format

### Ölçüm

| Soru | GGUF (q8_0) | Verdict |
|---|---|---|
| Başkent | `Ankara'dır.` (kısa; sonda hafif `</model>` artığı) | PASS |
| 2+2 | `4 eder.` | PASS |
| Merhaba | `Merhaba.` | PASS |

### Sonuç

**HF ✅ + GGUF/llama.cpp ✅ + MLC (Path A + q4f32) ❌**

Merge edilmiş LoRA ağırlıkları sağlam. Bozulma MLC `convert_weight` / quantize / serve zincirine izole.

Prod Docker (`q4f16_1` base) değiştirilmedi.

## 10. MLC q0f16 tanı — 2026-08-03 (KARMA / quantize güçlendiriyor)

HF `ayse-solmaz/gemma-2b-it-tr-q0f16`. Colab’da `MLCEngine` (Docker prod volume’a dokunulmadı). `q0f16` = no-quant, float16, BitsPerParam=16.

### Ölçüm (max_tokens=64, temperature=0)

| Soru | q0f16 MLC | Loop? | Verdict |
|---|---|---|---|
| Merhaba | İyi açılış sonra `SneakyThrows` / “Yeterli bir soruyu…” tekrarı | ✅ loop | FAIL form |
| Başkent | `Ankara'dır.` | ❌ | PASS |
| 2+2 | `4 eder.` | ❌ | PASS |
| Kendini tanıt | `Merhaba, kendim [ad]tir. İyi günlerdir.` | ❌ kısa garip | WEAK |

### Karşılaştırma tablosu

| Backend | Merhaba | Ankara | 2+2 | Loop |
|---|---|---|---|---|
| HF | ✅ | ✅ | ✅ | ❌ |
| GGUF q8 | ✅ | ✅ | ✅ | ❌ |
| MLC q4f16 FT | prefix sonra salata | ❌ | ❌ | ✅ |
| MLC q4f32 FT | prefix sonra salata | ❌ | ❌ | ✅ |
| MLC q0f16 FT | ❌ (açılış OK, sonra loop) | ✅ | ✅ | kısmi |

### Yorum

q0f16’da olgu soruları **temiz duruyor** (q4’teki “Ankara + salata” yok). Bu, **quantize hattının sorunu ciddi şekilde büyüttüğünü** gösterir.

Merhaba’da hâlâ MLC-only bozukluk var → tamamen “sadece q4” değil; convert/runtime/stop tarafında da artık daraltılabilir bir artık kalıyor.

## 7. Mevcut durum

| Öğe | Durum |
|---|---|
| Prodüksiyon modeli | Temel `gemma-2b-it-q4f16_1` (q4f32 denemesinden geri alındı, sağlıklı) |
| Volume | 38 shard, `q4f16_1` |
| Host yedek (pre-q4f32) | `backups/mlc-model-pre-q4f32-20260802-074402.tar.gz` |
| Host yedek (temiz Path A) | `backups/mlc-model-backup-20260802-034316.tar.gz` |
| Adaptör | `ayse-solmaz/gemma-2b-it-tr-lora` |
| q4f32 artifact | `ayse-solmaz/gemma-2b-it-tr-q4f32` (Cell 4 temiz, MLC serve bozuk) |
| q0f16 artifact | `ayse-solmaz/gemma-2b-it-tr-q0f16` (Colab MLCEngine: Ankara/2+2 PASS, Merhaba loop) |
| GGUF tanı | Colab q8_0 PASS (2026-08-03) |
| Ölçümler | `faz5-clean-before.json`, `faz5-q4f32-after.json` |

## 8. Path A / q4f32 kapandı — kalan yollar

1. ~~**Quantize patch**~~ — **ertelendi.** q4 FT salatası (LoRA outlier + group_size 32) kanıtlandı; şimdilik kovalanmıyor.
2. **q0f16 FT serve (aktif yol)** — MLC CPU’da 8-bit yok; ~5 GB yavaş ama doğru. Diag `:8088` → sonra prod.
3. Soft adapter + DeepKwiki (prod — MLC merge yolunu bypass) — yedek.
4. MLC’ye MRE issue — kanıt zinciri hazır, opsiyonel.

## 11. Karar: q0f16 FT deploy (2026-08-03)

**Neden q4 bırakıldı:** HF merge ✅, GGUF q8 ✅, MLC q4f16/q4f32 FT ❌ (prefix + salata). LoRA outlier’lar + MLC `group_size=32` q4’ü bozuyor. q0f16’da olgu soruları Colab’da temiz kesiliyor.

**Neden Merhaba blocker değil:** Chat downsample (1558→233) → OOD. Başarı = **factual 4/5**, Merhaba FAIL beklenen.

**Artefakt envanteri (Step 1) — 2026-08-03 gece:**

| Bileşen | HF `ayse-solmaz/gemma-2b-it-tr-q0f16` | Local `backups/q0f16-weights` |
|---|---|---|
| `params_shard_*.bin` (~5.05 GB, 0–48) | ✅ | ❌ partial: **25/49** shards, **~1.81 GB** (eksik: 0,4–9,15,30,33,35–48) |
| `tensor-cache.json` | ✅ | ❌ |
| `mlc-chat-config.json` (`q0f16`, stop `[1,107]`) | ✅ | ✅ |
| `gemma-cpu.so` q0f16 (2 239 336 B; ≠ prod q4f16_1) | ✅ | ✅ |
| tokenizer.* | ✅ | ❌ |

**Host HF download unreliable** (timeouts / process killed `4294967295`). Agent **does not block** on local fetch. User path: [`notebooks/mlc_q0f16_compile.md`](../notebooks/mlc_q0f16_compile.md) on Kaggle → reply `UPLOAD OK`. Diag compose mem **10G**. Prod **dokunulmadı**.

**Step 2/3 sonuç tablosu:** (diag seed sonrası — answer + `finish_reason`)


## 12. q4f16_2 embed-float FT — prod deploy (2026-08-05)

### Problem A (salad / stop) — SOLVED

**Root cause:** MLC q4 convert quantized model.embed_tokens.weight (and related embed path), destroying LoRA-sensitive embedding rows. Fine-tuned q4f16_1 / q4f32 artifacts produced prefix-then-salad or deygetNumberOfDereCiler() loops while stop tokens were configured correctly.

**Fix:** Re-convert with **embedding kept float16** (ormat: f32-to-bf16 on embed shard), quant q4f16_2, matching gemma-cpu.so compiled for q4f16_2. Diag volume :8088 verified first; same bytes promoted to prod volume mlc-model (no re-convert at swap).

| Check | Artifact |
|---|---|
| Host path | ackups/q4-embedfloat-weights/ |
| Diag volume | llm-monitoring-app_mlc-model-diag (identical layout) |
| Shards | 38 × params_shard_*.bin |
| Caches | 	ensor-cache.json + 
darray-cache.json (same file) |
| Config | mlc-chat-config.json — quantization: q4f16_2, conv_template.stop_token_ids: [1, 107] |
| lib | gemma-cpu.so — ELF x86-64, 1,764,464 B |

**Pre-swap backup:** ackups/mlc-model-pre-q4f16_2-20260805-102842.tar.gz (~1.14 GB).

### Problem B (project facts / DeepKwiki) — separate

Wrong answers with **clean inish_reason=stop** are expected until RAG/DeepKwiki. Not a rollback trigger.

### Six-Q (max_tokens=64, 	emperature=0, gateway :8080)

| Question | Before (q4f16_1 base) | After (q4f16_2 FT) | finish_reason |
|---|---|---|---|
| Türkiye'nin başkenti neresidir? | Abuja salata | Ankara'dır. | stop |
| 2+2 kaç eder? | 2'ye ulaşır salata | 4 eder. | stop |
| Su kaç derecede kaynar? | code-loop salata | -18 derece. | stop |
| Backend dili? | (run interrupted) | Node.js'dir. | stop |
| Access token süresi? | (run interrupted) | 1 saattir. | stop |
| Merhaba, nasılsın? | (run interrupted) | OOD loop-ish text | length |

**Diag vs prod after swap:** matches ackups/faz5-q4f16_2-embedfloat.json (same answers + finish_reason). **Problem A success:** 5/5 factual stop, no salad.

Artifacts: ackups/faz5-pre-q4f16_2-prod-baseline.json, ackups/faz5-post-q4f16_2-prod.json.

### Browser / stream check

localhost:3002 not running; verified equivalent via gateway SSE: question *Türkiye'nin başkenti neresidir?* streamed Ankara'dır. (~13s).

### Rollback

Not needed. Restore: mlc-model-pre-q4f16_2-20260805-102842.tar.gz into volume llm-monitoring-app_mlc-model if healthz/salad regress.
