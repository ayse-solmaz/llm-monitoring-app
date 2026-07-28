# Demo Day Runbook

## T-60 — Ayağa kaldırma

- [ ] Laptop prizde, güç planı "En yüksek performans"
- [ ] Bildirimler kapalı
- [ ] Docker Desktop açık
- [ ] `.\scripts\demo-up.ps1` → healthz ready + model-id assert
- [ ] Tarayıcı: http://localhost:3002/chat

## T-45 — Doğrulama

- [ ] `curl http://localhost:8080/healthz` → `"ready": true`
- [ ] `curl http://localhost:8080/v1/models` → `/app/model`
- [ ] `curl -N` streaming test (ilk satırlar: `: connected` / `data:`)
- [ ] http://localhost:3002/chat → Connect ok
- [ ] Render health → 200 (`https://llm-monitoring-api.onrender.com/api/v1/healthz`)
- [ ] Grafana → http://localhost:3000 (`admin` / `admin`)

## T-15 — Cache ısıtma

Demo sorularını bir kez sor (gateway LRU cache'e girer). Tekrarlarda `X-Cache: HIT` / anında yanıt.

## Demo (7 dakika)

1. **0:00–0:40** Açılış: "kendi altyapında LLM = ölçüm sorunu"
2. **0:40–1:20** Login → Dashboard (Vercel canlı)
3. **1:20–3:20** Chat: "Hi" → token'lar akıyor, TTFT göster (CPU: onlarca sn–dakika)
4. **3:20–4:10** Aynı soru → cache hit, anında
5. **4:10–5:10** Backend switch (CPU/GPU, bulunursa) / scale notu
6. **5:10–5:50** Admin: adapter swap (spec §4)
7. **5:50–7:00** Ölçekleme raporu ([docs/SCALING_REPORT.md](SCALING_REPORT.md))

## Kurtarma

- Streaming çöktü: Grafana'ya geç, incident / KPI demo
- Her şey çöktü: Ekran kaydı yedeği
- 504 / ready false: `demo-up` + healthz ready bekleyin; prewarm bitmeden Chat açmayın

## Yedekler

- [ ] Başarılı demonun mp4 kaydı
- [ ] Grafana paneli ekran görüntüsü
- [ ] SCALING_REPORT.md PDF / print

## Quick commands

```powershell
.\scripts\demo-up.ps1
cd frontend; npm run dev -- -p 3002
# Chat: http://localhost:3002/chat
# Grafana: http://localhost:3000
.\scripts\demo-down.ps1
```

Ölçüm referansı: [PERF_RESULTS.md](PERF_RESULTS.md) · Plan: [DEMO_MUST_PLAN.md](DEMO_MUST_PLAN.md)
