# Demo script (localhost — CPU)

Use this for a short live demo. **No Cloudflare tunnel.** One Chat message at a time.

## Before you start

1. Open **Docker Desktop** and wait until it is Running.
2. Terminal A — stack (1 replica for Chat):

```powershell
cd C:\Users\aysnu\llm-monitoring-app
docker compose up -d --scale mlc=1
docker compose ps
curl.exe http://localhost:8080/healthz
curl.exe http://localhost:8080/v1/models
```

Expect health `ok` and model id **`/app/model`**.

3. Terminal B — frontend (Grafana uses :3000):

```powershell
cd C:\Users\aysnu\llm-monitoring-app\frontend
npm run dev -- -p 3002
```

4. Login at http://localhost:3002 (Render API may take 30–60s to wake on first hit).

---

## Part A — Chat + scores (~5–8 min wall time on CPU)

1. Open http://localhost:3002/chat → **Connect** (should show Model ready).
2. Send **one** short message: `Hi` — do **not** send a second message until the first finishes (can take **2–5 minutes**).
3. Show: streamed reply, live TTFT / tok/s, ScoreCard (accept / review / reject).
4. Optional: http://localhost:3002/admin — adapter / temperature / top-p / max tokens (soft PEFT).
5. Optional: ask `KPI gateway nedir` for DeepKwiki injection.
6. Dashboard: http://localhost:3002/dashboard — session persisted to Render.

**Talking point:** Metrics are raw LLM signals; scoring is deterministic (latency + length + format).

---

## Part B — Throughput scale (optional, separate from single-request speed)

Scaling **does not** make one answer faster on one CPU; it finishes a **batch** of concurrent jobs sooner.

1. Terminal:

```powershell
cd C:\Users\aysnu\llm-monitoring-app
docker compose up -d --scale mlc=3
```

2. Grafana: http://localhost:3000 (`admin` / `admin`) → dashboard `mlc-scaling-cadvisor` — RPS, TTFT, inflight, replica count.
3. Cite measured results in [SCALING_REPORT.md](./SCALING_REPORT.md): 6 requests wall time **1061 s → 465 s** (−56%), throughput **~2.6×** with 3 replicas.
4. After the scale demo, return to Chat mode:

```powershell
docker compose up -d --scale mlc=1
```

---

## Shut down

```powershell
docker compose down
```

Ctrl+C in the frontend terminal. Leave Docker volumes unless you intentionally want a full reset (`-v` deletes the seeded model volume).

---

## Do not

- Rebuild `mlc-server-spike` (~1h+)
- Overlap Chat requests on CPU
- Promise Vercel → home-PC tunnel Chat (CF 524/530 vs CPU TTFT)
