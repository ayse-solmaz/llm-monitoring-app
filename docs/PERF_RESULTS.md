# Demo MUST — Performance Results

Measured: **2026-07-28** (local Docker MLC CPU Gemma 2B, warm process).

Path: `Browser/curl → localhost:3002/api/mlc → gateway:8080 → nginx → mlc`

## Summary card

| Metric | Result |
|--------|--------|
| TTFT (first token content) | **~17 077 ms** (~17 s, warm) |
| Early SSE flush (`: connected`) | **~332 ms** |
| Completion | **~47 s** total for `max_tokens=32` (~30 s after TTFT) |
| Approx. decode rate | **~0.7–1 tok/s** after first token (CPU) |
| 504 count | **0** |
| Concurrent 2nd request | **✓ queue** (`event: queue`, no error) |
| UI 2nd Send while streaming | **✓ lock** (`isStreaming` disables Send) |
| Cache HIT (repeat `"Hi"`) | **~73 ms**, `X-Cache: HIT` |
| Grafana dashboard | **✓** HTTP 200 (`/d/mlc-scaling-cadvisor`) |
| Render `/healthz` | **✓** HTTP 200 |

```
TTFT (ilk token): ~17077 ms (warm CPU; cold can be 1–2+ min)
Completion token'lar: ~30 sn'de ~32 max_tokens (parça parça SSE)
2. mesaj bitmeden 3. mesaj: [✓ kuyruk + ✓ UI kilit / ❌ error yok]
504 sayısı: 0
Grafana panel'i: [✓ açılıyor]
```

## Streaming curl (Next proxy)

```powershell
curl.exe -N -s http://localhost:3002/api/mlc/v1/chat/completions `
  -X POST -H "Content-Type: application/json" `
  -d "@perf_chat_hi.json"
```

Observed order:

1. `: connected` (~0.3 s) — Next early flush  
2. `: gateway-open` — gateway early flush  
3. `data: {... "content":"Hello" ...}` — first token (~17 s warm)  
4. Subsequent `data:` lines every ~1–2 s  
5. `data: [DONE]` (~47 s)

## Queue + lock

- Gateway `MAX_INFLIGHT=1`: second unique stream emits `event: queue` / `{"status":"waiting"}` until slot free; both complete without HTTP error when given enough time.
- Chat UI: Send disabled while `isStreaming` (client lock).

## Cache

Repeat identical `{"messages":[{"role":"user","content":"Hi"}],"max_tokens":32,"stream":true}`:

- `X-Cache: HIT`
- Full SSE replay in **~73 ms** (well under 300 ms demo target)
- Cached chunk id: `"cached"`

## Notes for Demo Day

- Expect **minutes** of TTFT on **cold** CPU after laptop sleep / first `demo-up`.
- Prewarm until `/healthz` `"ready": true` before jury Chat.
- Demo narrative: incremental tokens + measurable KPIs, not cloud-class latency.

## Prova log (2026-07-28)

| Prova | What | Result |
|-------|------|--------|
| 1 | Warm stack: stream + queue + cache + Grafana | Pass — TTFT ~17s, queue OK, cache 73ms, Grafana 200, 504=0 |
| 2 | `demo-down` + `demo-up` cold start (not full PC reboot) | Pass — ready in **~174 s** (~3 min); `/app/model` OK. Fixed `demo-up.ps1` `$i/$maxAttempts:` parse bug |
| Screen recording | OBS / Game Bar | **Not captured in this session** — record before Demo Day |

Full PC reboot prova remains a manual checklist item on the laptop.
