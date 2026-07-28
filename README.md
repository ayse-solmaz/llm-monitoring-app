<div align="center">
  <a href="https://academy.masterfabric.co">
    <img src="https://academy.masterfabric.co/academy-badge.png" width="120" alt="MasterFabric Academy">
  </a>
  <p><sub>academy.masterfabric.co is a <a href="https://masterfabric.co">MasterFabric</a> subsidiary.</sub></p>
</div>

---

# Raw LLM Monitoring & Decision Scoring App

LLM monitoring and deterministic decision scoring. The main **Chat** path runs **server-side Gemma 2B via MLC-LLM in Docker** (CPU inference, nginx load balancing). Soft PEFT (Admin adapters/prompts) is included; real LoRA weight swap is out of scope. Browser WebLLM remains at `/spike`. Sessions, messages, and scores persist to the Go backend (Render) and show on the dashboard.

## Live URLs

- **Frontend:** https://llm-monitoring-app.vercel.app
- **Backend health:** https://llm-monitoring-api.onrender.com/api/v1/healthz

**Requirements:** Chrome or Edge for the app UI. Server MLC needs Docker Desktop locally (see below). On the Render free tier, the first API request after idle may take 30–60 seconds to wake the service.

## Architecture (current)

```
Browser Chat → Next /api/mlc → KPI gateway :8080 → nginx (least_conn) → MLC×N (CPU)
                    ↘ JWT → Render Go API → Postgres (sessions / scores / dashboard)
```

`/spike` is a separate **browser WebLLM (WebGPU)** demo — not the main Chat path.

Demo day uses **localhost** (`:3002` + Docker). Cloudflare tunnel → Vercel Chat is **not** supported (CPU TTFT exceeds tunnel timeouts).

**Streaming (verified):** Next `/api/mlc` flushes SSE early (`: connected`) + `force-dynamic`; tokens arrive incrementally after CPU TTFT (warm ~17s, cold can be 1–2+ min). No 504 on the demo path. See [docs/PERF_RESULTS.md](docs/PERF_RESULTS.md) and [docs/DEMO_DAY_RUNBOOK.md](docs/DEMO_DAY_RUNBOOK.md).

## Local server-side MLC (Docker)

Public entry is the **KPI gateway**:

```powershell
cd C:\Users\aysnu\llm-monitoring-app
docker compose up -d --scale mlc=1
docker compose ps   # wait until mlc healthy
```

Use `--scale mlc=1` for Chat. Use `--scale mlc=3` only for throughput/scaling demos (does not speed up a single request on one CPU).

| Service | URL |
|---------|-----|
| Chat API (gateway) | http://localhost:8080/v1/chat/completions |
| Gateway metrics | http://localhost:8080/metrics |
| Gateway health | http://localhost:8080/healthz |
| Prometheus | http://localhost:9090 |
| Prometheus targets | http://localhost:9090/targets |
| cAdvisor | http://localhost:8081 |
| Grafana | http://localhost:3000 (`admin` / `admin`) |
| Dashboard | http://localhost:3000/d/mlc-scaling-cadvisor |

Frontend on **:3002** (Grafana owns :3000). Browser calls same-origin `/api/mlc`; Next proxies to `MLC_UPSTREAM` (or `NEXT_PUBLIC_MLC_URL`) → `http://127.0.0.1:8080`.

```powershell
cd frontend
npm run dev -- -p 3002
# Chat: http://localhost:3002/chat  — one message at a time (CPU is slow)

# Load test (3 concurrent ≈ replica count) — after: docker compose up -d --scale mlc=3
.\scripts\loadtest.ps1 -Total 10 -Concurrent 3

docker compose down
```

- Demo walkthrough: [docs/DEMO.md](docs/DEMO.md) · [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) · [docs/DEMO_MUST_PLAN.md](docs/DEMO_MUST_PLAN.md) · [docs/DEMO_DAY_RUNBOOK.md](docs/DEMO_DAY_RUNBOOK.md)
- Perf card: [docs/PERF_RESULTS.md](docs/PERF_RESULTS.md)
- Demo scripts: `.\scripts\demo-up.ps1` / `.\scripts\demo-down.ps1`
- Scaling write-up: [docs/SCALING_REPORT.md](docs/SCALING_REPORT.md)
- FINAL BOSS status: [docs/FINAL_BOSS_STATUS.md](docs/FINAL_BOSS_STATUS.md)

## Documentation

- [docs/API.md](docs/API.md) — architecture, endpoints, metrics & scoring
- [docs/MCP.md](docs/MCP.md) — MCP usage and local setup
- [docs/SCALING_REPORT.md](docs/SCALING_REPORT.md) — horizontal scaling (1 vs 3 replicas)
- [docs/PERFORMANCE_REVIEW.md](docs/PERFORMANCE_REVIEW.md) — performance audit and fixes
- [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) — security audit and remediation status
- [docs/DEMO.md](docs/DEMO.md) / [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) / [docs/DEMO_MUST_PLAN.md](docs/DEMO_MUST_PLAN.md) / [docs/DEMO_DAY_RUNBOOK.md](docs/DEMO_DAY_RUNBOOK.md) / [docs/PERF_RESULTS.md](docs/PERF_RESULTS.md) — run & present
- [archive/ADR-001-ollama-rejected.md](archive/ADR-001-ollama-rejected.md) — Ollama tried & rejected (MLC story kept); archived notes under `archive/`
