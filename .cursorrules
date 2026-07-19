# Project: Raw LLM Monitoring & Decision Scoring App
Deadline: July 21, 2026. Developer is a beginner; explain briefly what you do and why.

## Non-negotiable rules
1. Read PRD.md and MVP.md before any task. The 20-endpoint table in PRD §6 is the exact API contract — do not rename paths or invent extra endpoints.
2. Monorepo layout: /frontend (Next.js 14+ App Router, TypeScript) and /backend (Go 1.22+, Gin, GORM, PostgreSQL).
3. Never break the live deployment. After each phase the app must still work on Vercel/Render.
4. Keep it simple: no extra libraries beyond the approved stack unless asked. No tests beyond smoke tests. No design polish until Phase 5.
5. Secrets only via environment variables. Never commit .env. Provide .env.example.
6. Frontend calls backend via NEXT_PUBLIC_API_URL. Backend allows CORS only for localhost:3000 and the Vercel domain (env CORS_ORIGIN).
7. Auth: JWT access (15 min) + refresh (7 days), bcrypt password hashing. Protected routes use middleware.
8. All API responses use JSON envelope: {"data": ..., "error": null} or {"data": null, "error": {"code": "...", "message": "..."}}.
9. After finishing a task, print: (a) files changed, (b) how to run, (c) exact curl/browser steps for me to verify.
10. If something is ambiguous, choose the simplest option consistent with PRD.md and state your assumption. Do not wait.

## Approved stack
Frontend: next, react, typescript, tailwindcss, @mlc-ai/web-llm, recharts, zustand (state), zod (validation)
Backend: gin-gonic/gin, gorm.io/gorm + postgres driver, golang-jwt/jwt/v5, x/crypto/bcrypt, google/uuid
