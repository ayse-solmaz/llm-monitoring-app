# MCP & Local Setup

## Local setup

Backend is **[masterfabric-go](https://github.com/gurkanfikretgunak/masterfabric-go)** (Chi, DDD, goose migrations). LLM monitoring routes are added as an app module; Kafka and WebSocket are disabled by default.

### Prerequisites

- **Go** 1.26+
- **PostgreSQL** 16 (required — no SQLite)
- Optional: **Docker** for local Postgres/Redis (`backend/deployments/docker-compose.yml`)
- **Node.js** 20+ for frontend

### 1. Clone and configure

```bash
git clone https://github.com/ayse-solmaz/llm-monitoring-app.git
cd llm-monitoring-app
```

**Backend:**

```bash
cp backend/.env.example backend/.env
# Set DATABASE_URL to Postgres, JWT_SECRET (32+ bytes), CORS_ORIGIN
```

**Frontend:**

```bash
cp frontend/.env.example frontend/.env.local
```

### 2. Backend (Postgres)

```bash
cd backend
# Start Postgres (Docker):
docker compose -f deployments/docker-compose.yml up -d postgres

# Env example:
# DATABASE_URL=postgres://masterfabric:masterfabric@localhost:5432/masterfabric?sslmode=disable
# KAFKA_ENABLED=false
# WS_ENABLED=false

go run ./cmd/server
```

API: http://localhost:8080/api/v1

Migrations run automatically on startup (goose).

**Smoke test:**

```bash
$env:BASE_URL = "http://localhost:8080/api/v1"
./backend/scripts/smoke-test.ps1
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

### 4. Server-side MLC (Docker CPU)

The Chat UI calls **Docker MLC** through nginx (`NEXT_PUBLIC_MLC_URL`, default `http://localhost:8080`). Browser WebLLM remains at `/spike`.

> **Build note:** The `mlc-server-spike` image is a pinned CPU build (~**98 minutes** first time: pip + HF LFS + `mlc_llm compile`). Compose uses the already-built image — do not add a `build:` directive.

```powershell
# From repo root (image must already exist: mlc-server-spike)
docker compose up -d --scale mlc=3
docker compose ps   # wait for mlc healthy
```

| Port | Service |
|------|---------|
| 8080 | nginx → MLC `/v1/chat/completions` |
| 9090 | Prometheus (scrapes cAdvisor every 5s) |
| 8081 | cAdvisor |
| 3000 | Grafana (`admin`/`admin`) — conflicts with `npm run dev`; stop Grafana or move Next to another port when both local |

See [SCALING_REPORT.md](SCALING_REPORT.md).

### Environment variables

| Variable | Where | Description |
|----------|-------|-------------|
| `DATABASE_URL` | Backend | Postgres connection string (Render injects automatically) |
| `JWT_SECRET` | Backend | JWT signing secret (minimum 32 bytes) |
| `CORS_ORIGIN` / `CORS_ALLOWED_ORIGINS` | Backend | Allowed frontend origin |
| `PORT` | Backend | HTTP port (default 8080; use **8081** if Docker nginx owns 8080) |
| `KAFKA_ENABLED` | Backend | `false` for this app |
| `WS_ENABLED` | Backend | `false` for this app |
| `BUILD_VERSION` | Backend | Version string for `/version` |
| `GIT_COMMIT` | Backend | Commit hash for `/version` |
| `NEXT_PUBLIC_API_URL` | Frontend | Backend API prefix |
| `NEXT_PUBLIC_MLC_URL` | Frontend | Server MLC base (default `http://localhost:8080`) |

---

## MCP usage (Model Context Protocol)

This project was built and deployed using Cursor agent sessions with MCP tool servers.

### Render MCP

Used for backend infrastructure and operations:

- Created **PostgreSQL** instance (`llm-monitoring-db`, Oregon, Postgres 16)
- Created **web service** `llm-monitoring-api` (Docker, health check `/api/v1/healthz`)
- Set environment variables (`JWT_SECRET`, `CORS_ORIGIN`, etc.)
- Updated `CORS_ORIGIN` to `https://llm-monitoring-app.vercel.app` after frontend deploy
- Triggered redeploys and verified deploy status via `get_deploy` / `list_deploys`

> **Note:** Render MCP does not expose database connection strings, so `DATABASE_URL` was linked to the `llm-monitoring-db` Postgres instance manually in the [Render Dashboard](https://dashboard.render.com/web/srv-d9euanrtqb8s73b8136g). This connection is live — production smoke tests (auth + all 8 LLM endpoints) pass against the deployed API and Postgres.

### Vercel MCP

Used for frontend deployment monitoring and verification:

- Listed projects and deployments (`list_projects`, `list_deployments`)
- Monitored Git-triggered production builds (`get_deployment`, `get_deployment_build_logs`)
- Verified live routes with `web_fetch_vercel_url` (`/chat`, `/dashboard`)
- Production deploys are **Git-integrated** (repo `ayse-solmaz/llm-monitoring-app`, root directory `frontend`); pushes to `main` auto-deploy

> Initial file-upload deploy attempts via `deploy_to_vercel` were abandoned in favor of Git-linked deployment.

### MasterFabric Academy MCP

**Status: connected (local stdio server).**

Used for a full **auth and CORS security review** with mentor personas loaded via `get_mentor_persona`:

- **staff-engineer** — production readiness, operability, maintainability
- **security-coach** — AuthN/AuthZ, JWT/session handling, abuse controls, safe defaults

Review scope: `backend/internal/handlers/auth.go`, JWT middleware, and CORS configuration in `backend/internal/middleware/middleware.go`.

**17 findings** were identified across severity levels. All were implemented and verified live (local + production smoke tests):

| Category | Implemented |
|----------|-------------|
| Session security | Refresh token rotation, revoke-all on password change, idempotent logout, token capping on login |
| Abuse prevention | Per-IP rate limiting on `/auth/login` and `/auth/register` (10/min → 429) |
| Input validation | Email regex + 254-char cap, password 8–128 chars, 1 MB body limit on auth routes |
| CORS | `Access-Control-Max-Age: 86400` to reduce preflight overhead |

Configured in `.cursor/mcp.json` as `masterfabric-academy`, running the local MCP server from the MasterFabric Academy `one-hundered-days` repo.
