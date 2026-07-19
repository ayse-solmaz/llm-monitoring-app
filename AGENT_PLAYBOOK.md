# AGENT_PLAYBOOK.md — Orchestration Guide
> **Nasıl kullanılır (TR):** Bu dosya agent'lara İngilizce yazıldı çünkü kodlama agent'ları İngilizce talimatlarla daha tutarlı çalışır. Her fazda ilgili "PROMPT" bloğunu kopyalayıp agent'a ver. Fazın "DoD" (Definition of Done) listesini **sen kendin elinle** doğrula — agent "bitti" dedi diye geçme. Bu dosyayı, PRD.md ve MVP.md ile birlikte repo köküne koy; agent'a her oturumda "Read PRD.md, MVP.md and AGENT_PLAYBOOK.md first" de. Önerilen araç: Claude Code (kurulum ve dokümanlar: https://docs.claude.com/en/docs/claude-code/overview).

---

## PROJECT CONSTITUTION (paste into CLAUDE.md at repo root)

```
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
```

---

## PHASE 0 — Environment + WebLLM Spike (DO THIS FIRST)

### PROMPT 0.1 — Repo scaffold
```
Create a monorepo: /frontend (Next.js 14+ App Router, TypeScript, Tailwind) and /backend (Go module with Gin).
Add root README.md placeholder, .gitignore for both stacks, and CLAUDE.md with the project constitution I provide.
Do not add any features yet. Show me how to run both dev servers.
```

### PROMPT 0.2 — WebLLM spike (critical risk check)
```
In /frontend create a single spike page at /spike:
- Use @mlc-ai/web-llm to load model "gemma-2-2b-it-q4f16_1-MLC" via CreateMLCEngine.
- Show a progress bar bound to initProgressCallback.
- Detect WebGPU support first (navigator.gpu); if unsupported, show a clear warning listing supported browsers.
- One textarea + send button; stream the response with engine.chat.completions.create({stream: true}) and render tokens as they arrive.
- Log to console: time to first token (ms), total time (ms), and engine.runtimeStatsText() after completion.
Keep everything in one client component. No auth, no backend, no styling beyond basic layout.
If "gemma-2-2b-it-q4f16_1-MLC" is not in the current prebuilt model list of the installed web-llm version, list available Gemma variants and pick the smallest instruct variant, telling me which one you chose.
```
**DoD (verify yourself, TR):** Chrome'da /spike aç → model insin → cevap aksın → konsolda TTFT ve stats görün. Bu çalışmadan Faz 1'e geçme.

---

## PHASE 1 — Backend core (Config + Auth + CMN = 12 endpoints)

### PROMPT 1.1
```
Read PRD.md §6. In /backend implement with Gin + GORM + PostgreSQL:
- Models & migrations: users, refresh_tokens (PRD §6 data model).
- Endpoints, exactly these paths under /api/v1:
  CMN: GET /healthz (no DB dependency; returns {"status":"ok"}), GET /version
  Config: GET /config, GET /config/models (models list hardcoded from a Go slice for now, matching the WebLLM model ids)
  Auth (8): POST /auth/register, POST /auth/login, POST /auth/refresh, POST /auth/logout, GET /auth/me, PUT /auth/me, POST /auth/change-password, DELETE /auth/me
- JWT middleware for protected routes (everything under /auth except register/login/refresh).
- Config via env: PORT, DATABASE_URL, JWT_SECRET, CORS_ORIGIN. Provide .env.example.
- Use the JSON envelope from CLAUDE.md. Return proper status codes (400/401/404/409).
- Give me a smoke-test script (curl) covering: register, login, me, refresh, change-password, logout.
Use local Postgres via docker compose for development; include docker-compose.yml.
```
**DoD (TR):** Curl script'i baştan sona hatasız geçiyor; yanlış şifreyle 401 geliyor.

---

## PHASE 2 — First deployment (Render + Vercel via MCP)

### PROMPT 2.1 — Backend to Render
```
Prepare /backend for Render: multi-stage Dockerfile (build → distroless/alpine run), listen on $PORT, run GORM automigrate on start.
Then, using the Render MCP tools: create a PostgreSQL instance and a Web Service from this repo's /backend directory, set env vars (DATABASE_URL from the new Postgres, JWT_SECRET generated, CORS_ORIGIN=http://localhost:3000 for now), health check path /api/v1/healthz.
After deploy, verify /api/v1/healthz returns 200 from the public URL and show me the URL.
If Render MCP is not connected, stop and tell me exactly how to connect it instead of using the dashboard.
```

### PROMPT 2.2 — Frontend skeleton to Vercel
```
In /frontend create the SPA skeleton: routes /auth, /chat, /dashboard sharing one layout with a top nav (client-side transitions). Move the spike page content later — for now /chat can be a placeholder. Implement /auth with working register/login forms calling the live Render API (NEXT_PUBLIC_API_URL), storing tokens in memory + refresh flow, and route guard redirecting unauthenticated users to /auth.
Then, using the Vercel MCP tools: deploy /frontend, set NEXT_PUBLIC_API_URL to the Render URL. Give me the production URL.
Finally tell me the exact CORS_ORIGIN value to update on Render (the Vercel domain) and update it via Render MCP.
```
**DoD (TR):** Vercel URL'inde kayıt ol → giriş yap → /chat'e yönlen. Render URL/healthz 200. Bu andan itibaren canlı sistem hiç bozulmayacak.

---

## PHASE 3 — Inference view (WebLLM + metrics + scoring)

### PROMPT 3.1
```
Read PRD §4 View 2 and §5. Build /chat properly:
- Subview 2a: model selector fed from GET /config/models, load button, progress bar, WebGPU check with friendly fallback message.
- Subview 2b: chat UI with streaming responses (multi-turn within the session, history kept in memory/zustand).
- Subview 2c: live metrics panel updating during streaming: TTFT, tokens/sec, prompt tokens, completion tokens, elapsed time. After completion also show model load time and runtimeStatsText.
- Implement lib/scoring.ts exactly as PRD §5: latencyScore, lengthScore, formatScore (0-100 each, deterministic rules with documented thresholds), composite = weighted average (0.4/0.3/0.3), decision: accept>=70, review>=40, else reject. Show a score card under each assistant message.
No backend persistence yet. Keep the /spike page untouched as fallback.
```
**DoD (TR):** Canlıda (Vercel) chat çalışıyor, metrikler akış sırasında güncelleniyor, her cevabın altında skor kartı var.

---

## PHASE 4 — LLM endpoints + Dashboard (persistence)

### PROMPT 4.1 — Backend LLM endpoints (8)
```
Read PRD §6 WEB MLC-LLM table. Implement sessions, messages, scores models (PRD data model) and these endpoints, all JWT-protected and scoped to the authenticated user:
POST /llm/sessions, GET /llm/sessions (paginated ?page=&limit=), GET /llm/sessions/:id (include messages with their scores), DELETE /llm/sessions/:id,
POST /llm/sessions/:id/messages (accepts role, content, and metric fields), POST /llm/sessions/:id/scores (accepts message_id + score fields),
GET /llm/metrics/summary (avg ttft, avg tokens_per_sec, total tokens, session count), GET /llm/scores/summary (avg composite, counts by decision).
Extend the curl smoke script. Deploy to Render via Render MCP and verify live.
```

### PROMPT 4.2 — Wire frontend + Dashboard
```
1) In /chat: on model load create a session (POST /llm/sessions with model_id, device_info, model_load_ms). After each completed assistant message, POST the message with metrics, then POST its scores. Fire-and-forget with error toast; never block the chat stream.
2) Build /dashboard (PRD §4 View 3): 3a session list (paginated, newest first), 3b session detail (messages + metrics + score badges), 3c summary charts with recharts: avg tokens/sec over sessions (line), decision distribution (pie/bar), using the two summary endpoints.
Deploy to Vercel via Vercel MCP. Verify on production.
```
**DoD (TR):** Temiz tarayıcıda: register → chat'te 2-3 mesaj → dashboard'da oturum, metrikler ve grafikler görünüyor. Hepsi canlı URL'lerde.

---

## PHASE 5 — Delivery package

### PROMPT 5.1
```
Write the final root README.md in English:
- Project summary (Raw LLM Monitoring & Decision Scoring, MLC-LLM/WebLLM in-browser inference)
- Live URLs (Vercel frontend, Render backend healthz)
- Architecture diagram (mermaid): Browser(WebLLM/WebGPU) -> Next.js on Vercel -> Go API on Render -> PostgreSQL
- Full 20-endpoint table copied from PRD §6 with auth requirements
- Metrics & scoring methodology (thresholds and weights)
- Local setup instructions
- MCP usage section: Render MCP, Vercel MCP (what was done with each), MF Academy MCP status
- Known limitations (WebGPU browser support, Render cold start)
Also do a final sweep: remove dead code, ensure .env.example files are complete, verify /spike still works as fallback demo.
```
**DoD (TR):** MVP.md §4'teki tüm kutuları kendin işaretle. Render'ı uyandır (healthz'e istek at), gizli pencerede tam akışı bir kez daha oyna, teslim et.

---

## TROUBLESHOOTING CHEATSHEET (TR)

| Belirti | Agent'a söyle |
|---|---|
| Model listede yok hatası | "List prebuiltAppConfig.model_list from the installed web-llm version and switch to the closest Gemma instruct variant" |
| CORS hatası (console'da) | "Fix CORS: backend must allow origin <vercel-url> with credentials and Authorization header" |
| Render build fail | "Fetch the Render build logs via Render MCP and fix the Dockerfile accordingly" |
| 401 döngüsü | "Debug the refresh flow: log token expiry, ensure refresh runs once and retries the original request" |
| Chat kasıyor | "Move metric state updates to requestAnimationFrame batching; do not setState per token" |

## GOLDEN RULES (TR)
1. Aynı anda tek faz, tek agent görevi. Paralel büyük görev verme — çakışır.
2. Her fazdan sonra commit + push. Canlıyı bozan değişikliği hemen revert et.
3. Agent'ın "çalışıyor" demesi kanıt değildir; DoD adımlarını tarayıcıda/curl'de kendin yap.
4. Bir görev 30 dk'dan uzun süredir dönüyorsa durdur, görevi daha küçük parçaya böl.
5. Faz 0 spike'ı her şeyden önce gelir. O çalışmadan hiçbir şeye başlama.
