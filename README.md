<div align="center">
  <a href="https://academy.masterfabric.co">
    <img src="https://academy.masterfabric.co/academy-badge.png" width="120" alt="MasterFabric Academy">
  </a>
  <p><sub>academy.masterfabric.co is a <a href="https://masterfabric.co">MasterFabric</a> subsidiary.</sub></p>
</div>

---

# Raw LLM Monitoring & Decision Scoring App

LLM monitoring and deterministic decision scoring. The main **Chat** path runs **server-side Gemma 2B via MLC-LLM in Docker** (CPU inference, nginx load balancing). Browser WebLLM remains available as a demo at `/spike`. Sessions, messages, and scores are persisted to a Go backend and visualized on a monitoring dashboard.

## Live URLs

- **Frontend:** https://llm-monitoring-app.vercel.app
- **Backend health:** https://llm-monitoring-api.onrender.com/api/v1/healthz

**Requirements:** Chrome or Edge for the app UI. Server MLC needs Docker Desktop locally (see below). On the Render free tier, the first API request after idle may take 30–60 seconds to wake the service.

## Local server-side MLC (Docker)

MLC now runs **on the server** (Docker, CPU inference) — not only in the browser.

```powershell
cd C:\Users\aysnu\llm-monitoring-app

# Start nginx + 3 MLC replicas + Prometheus + cAdvisor + Grafana
docker compose up -d --scale mlc=3

# Wait until all mlc containers are healthy
docker compose ps
```

| Service | URL |
|---------|-----|
| MLC (via nginx) | http://localhost:8080/v1/chat/completions |
| Prometheus | http://localhost:9090 |
| Prometheus targets | http://localhost:9090/targets |
| cAdvisor | http://localhost:8081 |
| Grafana | http://localhost:3000 (`admin` / `admin`) |
| Dashboard | http://localhost:3000/d/mlc-scaling-cadvisor |

Frontend chat talks to `NEXT_PUBLIC_MLC_URL` (default `http://localhost:8080`).  
If Go API also needs a local port, use `PORT=8081` so it does not clash with nginx `:8080`.

```powershell
# Load test (3 concurrent ≈ replica count)
.\scripts\loadtest.ps1 -Total 10 -Concurrent 3

docker compose down
```

Scaling write-up: [docs/SCALING_REPORT.md](docs/SCALING_REPORT.md)

## Documentation

- [docs/API.md](docs/API.md) — architecture, endpoints, metrics & scoring
- [docs/MCP.md](docs/MCP.md) — MCP usage and local setup
- [docs/SCALING_REPORT.md](docs/SCALING_REPORT.md) — horizontal scaling (1 vs 3 replicas)
- [docs/PERFORMANCE_REVIEW.md](docs/PERFORMANCE_REVIEW.md) — performance audit and fixes
- [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) — security audit and remediation status
