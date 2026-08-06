# Faz 1.5 raporu — MLC yükleme yolu kanıtı

Tarih: 2026-07-31  
Kapsam: inceleme + CLI smoke. Eğitim yok. `mlc-server-spike` rebuild yok.

---

## 1. Base kimliği

| Alan | Değer |
|------|--------|
| HF / MLC kaynağı | `mlc-ai/gemma-2b-it-q4f16_1-MLC` → **`base_model: google/gemma-2b-it`** |
| `model_type` | `gemma` (Gemma 1 — **değil** `gemma2`) |
| Mimari kanıt | `hidden_size=2048`, `num_hidden_layers=18`, `intermediate_size=16384`, `num_key_value_heads=1` |
| `quantization` | **`q4f16_1`** |
| `conv_template` | **`gemma_instruction`** |
| `context_window_size` | **8192** |
| Serve lib | `/app/model/gemma-cpu.so` |

**Colab'da eğitilecek base (zorunlu aynı):** `google/gemma-2b-it`  

**YASAK:** `google/gemma-2-2b-it` (Gemma 2: 26 layer / hidden 2304) — adapter/mimari uymaz.

---

## 2. Swap mekaniği

- Named volume: **`llm-monitoring-app_mlc-model`**
- Mount: `mlc-model:/app/model:ro` (serve RO)
- İlk seed: `model-init` image’dan volume’a kopyalar; `gemma-cpu.so` varsa skip

**Karar: named volume — kolay swap.**  
Faz 5: yedek al → yeni MLC artifact’ı volume’a yaz (geçici RW / helper container) → `mlc` restart. Image rebuild gerekmez (spike rebuild yasak).

---

## 3. Convert Colab

Agent Colab çalıştıramaz. Smoke adımları: [`docs/FAZ15_COLAB_CONVERT_SMOKE.md`](FAZ15_COLAB_CONVERT_SMOKE.md)

**Durum:** kullanıcı testi bekleniyor → `[çalıştı ✅ / kırık ❌]` henüz boş.

---

## 4. Convert Docker (yedek)

Çalışan `mlc` container’da (`mlc-llm-cpu 0.20.0.dev0` / `mlc-ai-cpu 0.20.0`):

```
python3 -m mlc_llm → {compile, convert_weight, gen_config, chat, serve, ...}
python3 -m mlc_llm convert_weight --help → OK (q4f16_1 destekli)
```

Tam `google/gemma-2b-it` convert bu oturumda **çalıştırılmadı** (gated HF token + ~GB indirme + RO volume).  
Compile yolu image build’de daha önce kullanılmış (`Dockerfile` `mlc_llm compile … gemma-cpu.so`).

**Pratik yedek plan:** HF token ile one-shot Linux container (aynı image) + RW bind mount → `convert_weight` + `gen_config` + `compile` → çıktıyı `mlc-model` volume’a kopyala.

---

## 5. Özet kutu

```
1. base kimliği: gemma-2b-it (Gemma 1) / q4f16_1 / conv_template: gemma_instruction
   → Colab'da eğitilecek base: google/gemma-2b-it  (AYNI — gemma-2-2b-it YASAK)
2. swap mekaniği: named volume (llm-monitoring-app_mlc-model) — kolay
3. convert Colab'da: [kullanıcı smoke bekleniyor]
4. convert Docker'da: CLI kanıtlandı (convert_weight/gen_config/compile mevcut); full convert henüz koşulmadı
5. gated gemma erişimi: [kullanıcı kontrol etmeli — huggingface.co/google/gemma-2b-it]

→ YOL DURUMU: KOŞULLU AÇIK
   - Swap + base eşleşmesi: AÇIK
   - Convert: Docker CLI hazır (yedek); Colab smoke = senin 10–20 dk’lık işin
   - Colab ✅ veya Docker full convert ✅ olunca → AÇIK — Faz 2/3’e geç
   - İkisi de ❌ → KAPALI — strateji değiştir
```

---

## Senin sıradaki 2 iş

1. HF’de `google/gemma-2b-it` lisansını kabul et.
2. [`FAZ15_COLAB_CONVERT_SMOKE.md`](FAZ15_COLAB_CONVERT_SMOKE.md) hücrelerini çalıştır; sonucu agent’a yapıştır.

Alternatif: HF token ver → agent Docker içinde full convert smoke dener (eğitim değil, küçük yol testi).
