# Raw LLM Monitoring & Decision Scoring App

Monorepo scaffold for a browser-based LLM monitoring and decision scoring application.

## Structure

```
/
├── frontend/   Next.js 14+ (App Router, TypeScript, Tailwind)
├── backend/    Go 1.22+ (Gin)
├── PRD.md      Product requirements
├── MVP.md      Scope and timeline
└── AGENT_PLAYBOOK.md  Agent orchestration guide
```

## Local development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Backend

```bash
cd backend
go run ./cmd/server
```

API runs at [http://localhost:8080](http://localhost:8080).

## Status

Phase 0 — scaffold only. Features coming in later phases.
