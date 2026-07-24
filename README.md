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

MLC runs **on the server** (Docker, CPU). Public entry is the **KPI gateway**:

```
Client → gateway:8080 → nginx (least_conn) → mlc×N
              ↓ /metrics
         Prometheus → Grafana
```

```powershell
cd C:\Users\aysnu\llm-monitoring-app
docker compose up -d --scale mlc=3
docker compose ps   # wait until mlc healthy
```

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

Frontend: `NEXT_PUBLIC_MLC_URL=http://localhost:8080` (gateway). Use Next on **:3002** if Grafana owns :3000.

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
