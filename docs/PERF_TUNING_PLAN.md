# Performans ayar planı — kaynak çekişmesi

Tarih: 2026-08-01
Durum: **Onay bekliyor, uygulanmadı**

## Amaç

Yerel MLC yığınında ölçülen gecikmeyi düşürmek ve konteynerler arası CPU çekişmesini azaltmak.

**Kapsam dışı:** cevap kalitesi / olgusal doğruluk. Bu plan modelin *ne söylediğini* değil, *ne hızda söylediğini* hedefliyor. İkisi ayrı iş.

## Ölçülen sorunlar (2026-08-01, bu makinede)

| Bulgu | Kanıt |
|---|---|
| Thread / CPU kotası uyumsuzluğu | Konteyner `cpu.max = 400000 100000` (4 CPU) ama `TVM_NUM_THREADS=8`. `cpu.stat`: `nr_throttled 441`, `throttled_usec 170.030.960` (~170 sn) |
| İzleme yığını çıkarımla yarışıyor | Boştaki `docker stats`: cadvisor %13,57 — `mlc`'nin (%0,33) 40 katı |
| Agresif tarama | `prometheus.yml` `scrape_interval: 5s`, iki hedef birden |
| Ölçekleme hiç devreye girmiyor | Gateway `MAX_INFLIGHT=1` iken `--scale mlc=3` anlamsız; nginx `least_conn` dengeleyecek eşzamanlı yük göremiyor |
| Uçtan uca gecikme | 32 token / 181 sn ≈ **5,7 sn/token** |

Host: 8 çekirdek, 15,31 GiB RAM.

---

## Değişiklikler

### A. CPU ve thread sayısını eşitle — `docker-compose.yml` (`mlc` servisi)

| Alan | Şu an (diskte) | Olacak | Neden |
|---|---|---|---|
| `deploy.resources.limits.cpus` | `"8.0"` | `"6.0"` | 8 çekirdeğin tamamını modele vermek, cadvisor/Prometheus/Grafana ve işletim sistemi hâlâ CPU isterken host seviyesinde aşırı abonelik yaratır |
| `TVM_NUM_THREADS` | `"8"` | `"6"` | **Asıl kural: thread sayısı kotaya eşit olmalı.** Fazlası cgroup throttle üretir |
| `OMP_NUM_THREADS` | `"8"` | `"6"` | aynı |
| `--mode interactive` | eklendi | kalıyor | Tek kullanıcılı demo; `max_batch=1`, KV cache küçülür |

> Not: `cpus` değeri bu oturumda `4.0` → `8.0` yapılmıştı. İnceleme sonrası `6.0` daha dengeli görünüyor. Nihai değer değil, ölçümle doğrulanacak.

### B. Prometheus tarama aralığını gevşet — `prometheus/prometheus.yml`

`scrape_interval` ve `evaluation_interval`: `5s` → `15s`.

Üç kat daha az tarama. Grafana grafikleri biraz daha kaba olur, demo için fazlasıyla yeterli.

### C. Demo sırasında cadvisor'ı durdur — yalnızca belge

cadvisor compose'dan **kaldırılmıyor**; Grafana'daki konteyner panelleri `FINAL_BOSS_STATUS`'ta "Done" olarak işaretli bir özellik ve onu bozmak istemiyoruz.

Bunun yerine `docs/DEMO_DAY_RUNBOOK.md`'ye iki satır eklenecek:

```powershell
docker compose stop cadvisor    # demo öncesi — CPU'yu modele bırak
docker compose start cadvisor   # demo sonrası — konteyner panelleri geri gelsin
```

LLM metrikleri gateway'den geldiği için demo sırasında hiçbir KPI kaybolmaz; yalnızca konteyner CPU/bellek panelleri boş kalır.

### D. Ölçekleme tutarsızlığını belgele — kod yorumu + `FINAL_BOSS_STATUS.md`

`MAX_INFLIGHT` varsayılanı **değişmiyor** (`1` bu donanım için doğru karar). Yapılacak tek şey gerçeği yazmak:

- `docker-compose.yml` başlığındaki `--scale mlc=3` önerisinin yanına, gateway `MAX_INFLIGHT=1` iken ek replikaların iş görmeyeceği notu
- `FINAL_BOSS_STATUS.md`'deki "Shared weights + scale → Done" satırına, yük dengelemenin altyapı olarak hazır ama tek eşzamanlı istek sınırı yüzünden canlıda hiç tetiklenmediği notu
- Her replikanın ~2,8 GB RAM tuttuğu, 3 replikanın 15,31 GB'lık makinede ~8,5 GB'ı boşuna harcayacağı

### E. Grafana portu — DEĞİŞTİRİLMEYECEK

İncelendi ve vazgeçildi. Grafana'nın host'ta 3000'i tutması Next.js'i 3002'ye itiyor, ama `3000` şu yerlerde sabit geçiyor:

`README.md`, `docs/DEMO_DAY_RUNBOOK.md`, `docs/FINAL_BOSS_STATUS.md`, `docs/DEMO_MUST_PLAN.md`, `docs/PERF_RESULTS.md`, `frontend/src/components/admin/AdminLlmPanel.tsx` (sabit `href`), `mlc-gateway/main.py` (CORS listesi) ve `datasets/train.jsonl` (*"Grafana 3000 portunda çalışır"* — taşırsak eğitim verisi yanlış olur).

Taşımanın maliyeti faydasından yüksek. Yapılacak tek şey `README.md`'de 3002 kuralının nedenini netleştirmek.

---

## Ölçüm protokolü

Değişiklik yapmadan önce ve sonra aynı adımlar:

1. `docker compose restart gateway` — LRU önbelleği temizle, yoksa ikinci ölçüm sahte hızlı çıkar
2. `python scripts/bench_latency.py <etiket> --tokens 24`
3. Sonuç `docs/bench/<etiket>.json` altına yazılır

Betik TTFT (prefill maliyeti) ile decode hızını (token/sn) **ayrı** ölçer; ikisi farklı şeylerdir.

Uygulama sırası: `before-tuning` ölç → değişiklikleri uygula → `docker compose up -d` → `mlc` healthy olana kadar bekle (`start_period: 120s`) → `after-tuning` ölç.

## Başarı ölçütü

| Ölçüt | Hedef |
|---|---|
| `cpu.stat` → `throttled_usec` artışı | ~0 (throttle durmalı) |
| decode token/sn | en az %30 artış |
| Cevap **içeriği** | **değişmemeli** — bu değişiklikler kaliteyi etkilemez; etkiliyorsa bir varsayım yanlış demektir |

## Geri alma

Üç dosya değişiyor: `docker-compose.yml`, `prometheus/prometheus.yml`, `docs/DEMO_DAY_RUNBOOK.md`. Hiçbiri model ağırlıklarına veya volume'a dokunmuyor. `git checkout` + `docker compose up -d` ile eski hale döner. Canlı Render/Vercel dağıtımları bu plandan hiç etkilenmiyor.

---

## Bilinçli olarak ertelenenler

**`q4f32_1`'e yeniden derleme.** Model şu an `q4f16_1` ile CPU'da çalışıyor. x86 işlemcilerin çoğunda yerel fp16 aritmetiği yoktur; TVM her işlemde fp32'ye çevirip geri döner. MLC'nin kendi rehberi CPU hedefleri için `q4f32_1` önerir. **Bu muhtemelen buradaki en büyük hız kazancıdır**, ama `convert_weight` + `compile` ile yeni bir `.so` üretmeyi gerektirir — ayrı ve daha riskli bir iş. Bu plandan sonra ayrıca değerlendirilmeli.

**Cevap kalitesi.** Temel model hâlâ "Türkiye'nin başkenti" sorusuna yanlış cevap veriyor. Çözüm yolu DeepKwiki/bağlam enjeksiyonu; ayrı plan.
