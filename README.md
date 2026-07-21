# Raw LLM Monitoring & Decision Scoring App

A browser-based LLM monitoring and decision-scoring application. Inference runs **entirely in the user's browser** via [MLC-LLM / WebLLM](https://webllm.mlc.ai/) (`@mlc-ai/web-llm`) on **WebGPU** — no server-side model hosting. The app collects raw performance metrics (TTFT, tokens/sec, token counts), applies deterministic rule-based scoring, persists data to a Go backend, and visualizes history on a dashboard.

**Default model:** `gemma-2-2b-it-q4f16_1-MLC` (with smaller Gemma fallbacks when unavailable).

---

## Live URLs

| Service | URL |
|---------|-----|
| **Frontend (Vercel)** | https://llm-monitoring-app.vercel.app |
| **Backend health check** | https://llm-monitoring-api.onrender.com/api/v1/healthz |
| **Backend API base** | https://llm-monitoring-api.onrender.com/api/v1 |

**Quick check:** `curl https://llm-monitoring-api.onrender.com/api/v1/healthz` → `{"status":"ok"}`

**WebLLM fallback demo (no auth):** https://llm-monitoring-app.vercel.app/spike

---

## Architecture

```mermaid
flowchart LR
  subgraph Browser["Browser"]
    WebGPU["WebGPU"]
    WebLLM["WebLLM / Gemma"]
    Metrics["Metrics + Scoring"]
  end

  subgraph Vercel["Vercel"]
    NextJS["Next.js SPA\n/auth · /chat · /dashboard"]
  end

  subgraph Render["Render"]
    GoAPI["Go API\nGin + JWT"]
    Postgres[("PostgreSQL")]
  end

  WebGPU --> WebLLM
  WebLLM --> Metrics
  Metrics -->|"REST (JWT)"| NextJS
  NextJS -->|"NEXT_PUBLIC_API_URL"| GoAPI
  GoAPI --> Postgres
```

**Flow:** User authenticates on the Next.js SPA → loads a model in-browser (WebGPU) → streams chat with live metrics → scores computed client-side → sessions/messages/scores saved to Render Postgres via the Go API → dashboard reads aggregated history.

---

## Repository structure

```
/
├── frontend/     Next.js 14 App Router (TypeScript, Tailwind, Recharts)
├── backend/      Go 1.22+ (Gin, GORM, JWT)
├── PRD.md        Product requirements
├── MVP.md        Scope and delivery checklist
├── render.yaml   Render blueprint reference
└── AGENT_PLAYBOOK.md
```

---

## API — 20 endpoints (`/api/v1`)

All JSON responses (except `/healthz`) use the envelope: `{ "data": …, "error": null }`.

| # | Group | Method | Path | Auth | Description |
|---|-------|--------|------|------|-------------|
| 1 | Config | GET | `/config` | Public | App config, feature flags, scoring weights/thresholds |
| 2 | Config | GET | `/config/models` | Public | Supported WebLLM model list |
| 3 | Auth | POST | `/auth/register` | Public | Register (email + password, bcrypt) |
| 4 | Auth | POST | `/auth/login` | Public | Login → access + refresh tokens |
| 5 | Auth | POST | `/auth/refresh` | Public | Rotate refresh token → new access + refresh tokens |
| 6 | Auth | POST | `/auth/logout` | Public | Revoke refresh token |
| 7 | Auth | GET | `/auth/me` | **JWT** | Current user profile |
| 8 | Auth | PUT | `/auth/me` | **JWT** | Update profile |
| 9 | Auth | POST | `/auth/change-password` | **JWT** | Change password |
| 10 | Auth | DELETE | `/auth/me` | **JWT** | Delete account |
| 11 | LLM | POST | `/llm/sessions` | **JWT** | Create chat session (model, device, load time) |
| 12 | LLM | GET | `/llm/sessions?page=&limit=` | **JWT** | Paginated session list (newest first) |
| 13 | LLM | GET | `/llm/sessions/:id` | **JWT** | Session detail (messages + scores) |
| 14 | LLM | DELETE | `/llm/sessions/:id` | **JWT** | Delete session (cascade) |
| 15 | LLM | POST | `/llm/sessions/:id/messages` | **JWT** | Save message + raw metrics |
| 16 | LLM | POST | `/llm/sessions/:id/scores` | **JWT** | Save decision scores for a message |
| 17 | LLM | GET | `/llm/metrics/summary` | **JWT** | Avg TTFT, avg tok/s, total tokens, session count |
| 18 | LLM | GET | `/llm/scores/summary` | **JWT** | Avg composite, accept/review/reject counts |
| 19 | CMN | GET | `/healthz` | Public | Health check (Render probe; no DB) |
| 20 | CMN | GET | `/version` | Public | Build version + git commit |

**Total:** Config 2 + Auth 8 + LLM 8 + CMN 2 = **20 endpoints**.

---

## Metrics & scoring methodology

### Raw metrics (client-side, during inference)

| Metric | Source |
|--------|--------|
| TTFT (ms) | Request start → first streamed token |
| Tokens/sec | Completion tokens ÷ decode duration |
| Prompt / completion tokens | WebLLM usage or character estimate (~4 chars/token) |
| Total elapsed (ms) | Request start → stream end |
| Model load time (ms) | `CreateMLCEngine` init duration |
| Runtime stats | `engine.runtimeStatsText()` after completion |

### Decision scoring (`frontend/src/lib/scoring.ts`)

Rule-based, deterministic, 0–100 per dimension. Implemented in the browser; results POSTed to the backend.

**Composite (weighted average):**

| Dimension | Weight |
|-----------|--------|
| Latency | 0.4 |
| Length | 0.3 |
| Format | 0.3 |

**Decision thresholds:**

| Composite | Decision |
|-----------|----------|
| ≥ 70 | **accept** |
| ≥ 40 | **review** |
| < 40 | **reject** |

**Latency score** (average of TTFT + throughput sub-scores):

| TTFT | Score | Tokens/sec | Score |
|------|-------|------------|-------|
| ≤ 500 ms | 100 | ≥ 25 | 100 |
| ≤ 1000 ms | 85 | ≥ 15 | 85 |
| ≤ 2000 ms | 65 | ≥ 10 | 65 |
| ≤ 5000 ms | 40 | ≥ 5 | 40 |
| > 5000 ms | 15 | < 5 | 15 |

**Length score** — completion/prompt token ratio:

| Ratio | Score |
|-------|-------|
| 0.5 – 3.0 (ideal) | 100 |
| < 0.2 | 25 |
| < 0.5 | 60 |
| 3 – 6 | 70 |
| 6 – 12 | 45 |
| > 12 | 20 |

**Format score** — starts at 50; ends with sentence punctuation (+25) or truncated (−25); repetition via 4-gram analysis (+25 / +10 / −20).

---

## Local setup

### Prerequisites

- **Node.js** 20+
- **Go** 1.22+
- **Chrome or Edge** 113+ (WebGPU) for inference
- Optional: **Docker** for local Postgres

### 1. Clone and configure

```bash
git clone https://github.com/ayse-solmaz/llm-monitoring-app.git
cd llm-monitoring-app
```

**Backend** — copy env and edit secrets:

```bash
cp backend/.env.example backend/.env
```

**Frontend** — copy env:

```bash
cp frontend/.env.example frontend/.env.local
```

### 2. Backend

**SQLite (default, no Docker):**

```bash
cd backend
# DATABASE_URL=dev.db in .env
go run ./cmd/server
```

**PostgreSQL (Docker):**

```bash
cd backend
docker compose up -d
# Set DATABASE_URL=postgres://llm:llm@localhost:5432/llm_monitoring?sslmode=disable in .env
go run ./cmd/server
```

API: http://localhost:8080/api/v1

**Smoke test:**

```bash
# Bash
BASE_URL=http://localhost:8080/api/v1 ./backend/scripts/smoke-test.sh

# PowerShell
$env:BASE_URL = "http://localhost:8080/api/v1"
./backend/scripts/smoke-test.ps1
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 → register → `/chat` (inference) or `/spike` (standalone WebLLM demo).

### Environment variables

| Variable | Where | Description |
|----------|-------|-------------|
| `DATABASE_URL` | Backend | `dev.db` (SQLite) or Postgres connection string |
| `JWT_SECRET` | Backend | Secret for signing JWTs |
| `CORS_ORIGIN` | Backend | Allowed frontend origin (e.g. `http://localhost:3000`) |
| `PORT` | Backend | HTTP port (default `8080`) |
| `BUILD_VERSION` | Backend | Version string for `/version` |
| `GIT_COMMIT` | Backend | Commit hash for `/version` |
| `NEXT_PUBLIC_API_URL` | Frontend | Backend API prefix (e.g. `http://localhost:8080/api/v1`) |

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

---

## Known limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **WebGPU required** | Inference fails on unsupported browsers | Use Chrome/Edge 113+; `/spike` and `/chat` show a friendly fallback message; `/dashboard` still works |
| **Render free-tier cold start** | First API request after idle may take 30–60 s | Wake service before demos: `curl …/healthz` |
| **Client-side model download** | First load downloads ~GB model weights | Use 2B quantized model; load once and cache in browser |
| **Rule-based scoring only** | No LLM-as-judge | Deterministic thresholds documented above; v2 could add judge model |
| **No mobile WebGPU** | Poor mobile inference support | Desktop Chrome recommended for chat |

---

## Frontend views

| Route | Description |
|-------|-------------|
| `/auth` | Login / register |
| `/chat` | Model loader, streaming chat, live metrics, scoring, backend persistence |
| `/dashboard` | Session list, detail, summary charts (Recharts) |
| `/spike` | Standalone WebLLM spike (no auth, fallback demo) |

---

## License

Academic / portfolio project — see repository owner for terms.
