# AppSec Security Audit Report

**Scope:** `llm-monitoring-app` — Go/Gin backend + Next.js frontend  
**Methodology:** SAST/SCA perspective, OWASP Top 10 (2021) mapping, handler/auth/ORM/client flow code review  
**Overall:** Classic injection (SQLi, SSRF, OS command) and IDOR vectors are **well controlled**. Primary risk areas: **business logic integrity** (client-supplied metrics/scores), **security configuration** (headers/Gin mode/JWT secret policy), and **resource consumption**.

---

## Remediation status

### Implemented in this commit

1. **Security headers** (`frontend/next.config.mjs`): `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security: max-age=31536000; includeSubDomains`, `Referrer-Policy: strict-origin-when-cross-origin`. Content-Security-Policy intentionally **not** added (see accepted risks).
2. **JWT secret minimum length** (`backend/internal/config/config.go`): startup fails if `len(JWT_SECRET) < 32` with a clear error. Render production secret verified at **64 bytes** (deployment history); no rotation required.
3. **Gin release mode default** (`backend/cmd/server/main.go`): if `GIN_MODE` is empty, `gin.SetMode(gin.ReleaseMode)` before router init.
4. **LLM input validation** (`backend/internal/handlers/llm.go`): `role` must be exactly `user` or `assistant`; `content` max 65536 chars; `device_info` max 512; `model_id` max 128; reject negative `ttft_ms`, `tokens_per_sec`, token counts, `total_ms`, `model_load_ms`; scores 0–100 and decision `accept`/`review`/`reject` (existing checks retained).
5. **Rate limiting on refresh/logout** (`backend/internal/router/router.go`): `RateLimitAuth()` applied to `POST /auth/refresh` and `POST /auth/logout`.

### Previously implemented and verified by this audit

| Area | Status |
|------|--------|
| **SQL Injection** | GORM placeholders + Raw SQL `?` binding — no leaks |
| **IDOR** | All LLM queries filter by `user_id` (`loadOwnedSession`, `Where("user_id = ?")`) |
| **SSRF** | No outbound HTTP client |
| **Deserialization** | No unsafe pickle/yaml; JSON struct binding |
| **JWT alg confusion** | `HS256` enforced, `type: access` claim check |
| **Refresh token storage** | SHA-256 hash in DB; rotation active |
| **Password hashing** | bcrypt cost=12 |
| **Body limit** | Auth + LLM groups at 1MB (`router.go`) |
| **CORS** | Single origin from env; not wildcard |
| **Hardcoded secrets** | None in code; `.env` gitignored |
| **XSS (frontend render)** | No `dangerouslySetInnerHTML`; React escape |

### Accepted risks / future work

- **Client-supplied metrics/scores trust** — inherent to browser-side inference architecture; the server stores client-reported timings and scores without recomputation. **Planned:** server-side score recomputation and integrity checks.
- **Assistant role submission** — required by the in-browser inference flow (assistant messages posted after local WebLLM generation). **Partial mitigation:** strict `role` validation (`user` or `assistant` only); future signed payloads or server-only scoring pipeline.
- **Content-Security-Policy (CSP)** — deferred due to WebLLM WASM/CDN compatibility (Hugging Face model downloads, `@mlc-ai/web-llm`). Non-CSP headers added; CSP to be introduced with a WebLLM-compatible policy.
- **Account enumeration on register** — `409 conflict` on duplicate email reveals registered addresses; privacy-preserving registration deferred.
- **GetSession pagination** — `GET /sessions/:id` loads all messages without pagination; DoS via large sessions accepted for now.
- **Password complexity** — minimum length only; zxcvbn/HIBP checks deferred.
- **CAPTCHA / email verification** — open registration with IP rate limit only; bot/spam mitigation deferred.

---

## Critical / High Findings

### 1. Client-supplied score and metric manipulation

- **OWASP:** A08:2021 Software and Data Integrity Failures / A04:2021 Insecure Design
- **Severity:** **High**
- **Exploit:** Authenticated attacker sends `POST /api/v1/llm/sessions/:id/messages` with `role: "assistant"`, fake `ttft_ms` / `tokens_per_sec`, then `POST .../scores` with `decision: "accept"`, `composite: 100` to manipulate dashboard metrics and decision distribution. Server does not recompute scores (`llm.go`).
- **Remediation:** Server-side scoring only; client sends raw content/timing. Assistant messages from trusted pipeline only.

### 2. Assistant role spoofing (message forgery)

- **OWASP:** A01:2021 Broken Access Control
- **Severity:** **High**
- **Exploit:** Any authenticated user can POST `role: "assistant"` to inject fake assistant replies into session history.
- **Remediation:** Restrict API to `user` role only, or HMAC-signed client assertions for assistant messages. **Accepted** for current architecture with strict validation.

### 3. Missing security headers (CSP, HSTS, X-Frame-Options)

- **OWASP:** A05:2021 Security Misconfiguration
- **Severity:** **High** (XSS impact amplification)
- **Exploit:** Without CSP/X-Frame-Options, XSS or clickjacking can amplify impact on auth flows.
- **Remediation:** **Partially implemented** — non-CSP headers added; CSP deferred (WebLLM).

### 4. JWT secret entropy validation

- **OWASP:** A02:2021 Cryptographic Failures
- **Severity:** **High** (Critical if weak secret deployed)
- **Exploit:** Short or guessable `JWT_SECRET` enables HS256 token forgery.
- **Remediation:** **Implemented** — minimum 32-byte check at startup.

---

## Medium Findings

### 5. GetSession — unbounded message load (DoS)

- **OWASP:** A04:2021 Insecure Design
- **Severity:** **Medium**
- **Exploit:** Large message counts/content bloat `GET /sessions/:id` memory/DB load.
- **Remediation:** Paginate messages; field max lengths. **Partial:** field length limits added; pagination deferred.

### 6. Account enumeration

- **OWASP:** A07:2021 Identification and Authentication Failures
- **Severity:** **Medium**
- **Exploit:** Register returns `409` for existing email; login returns generic error — email list enumeration.
- **Remediation:** Generic responses; deferred.

### 7. `/auth/refresh` and `/auth/logout` without rate limit

- **OWASP:** A04:2021 Insecure Design
- **Severity:** **Medium**
- **Exploit:** High-volume refresh requests amplify DB/CPU load.
- **Remediation:** **Implemented** — IP rate limit on refresh and logout.

### 8. Missing field length validation

- **OWASP:** A04:2021 Insecure Design
- **Severity:** **Medium**
- **Exploit:** Large `content`/`device_info` within 1MB body inflates storage.
- **Remediation:** **Implemented** for LLM fields (content, device_info, model_id).

### 9. Refresh token in JavaScript memory

- **OWASP:** A07:2021 Identification and Authentication Failures
- **Severity:** **Medium** (XSS-dependent)
- **Exploit:** XSS can exfiltrate refresh token from auth store.
- **Remediation:** HttpOnly Secure cookie + CSRF; deferred (BFF pattern).

### 10. Gin debug mode production default

- **OWASP:** A05:2021 Security Misconfiguration
- **Severity:** **Medium**
- **Exploit:** Debug mode may leak stack traces and verbose logs.
- **Remediation:** **Implemented** — default to release mode when `GIN_MODE` unset.

---

## Low Findings

### 11. Weak password complexity

- **OWASP:** A07:2021
- **Severity:** **Low**
- **Remediation:** zxcvbn/HIBP; deferred.

### 12. Open registration (no CAPTCHA / email verification)

- **OWASP:** A04:2021
- **Severity:** **Low**
- **Remediation:** CAPTCHA, email verification; deferred.

### 13. Negative metric values accepted

- **OWASP:** A03:2021 (data integrity)
- **Severity:** **Low**
- **Remediation:** **Implemented** — reject negative numeric metrics.

---

## Priority Matrix

| Priority | Finding | OWASP | Status |
|----------|---------|-------|--------|
| **P0** | Client-supplied score/metric trust | A08, A04 | Accepted / planned |
| **P0** | Assistant role spoofing | A01 | Partial mitigation |
| **P1** | Security headers | A05 | Implemented (no CSP) |
| **P1** | JWT secret minimum entropy | A02 | Implemented |
| **P2** | GetSession DoS / pagination | A04 | Accepted |
| **P2** | Refresh rate limit | A04 | Implemented |
| **P2** | Account enumeration | A07 | Accepted |
| **P3** | Field limits, Gin release, password policy | A04, A05, A07 | Partial |

---

## Conclusion

The codebase is **mature against classic web vulnerabilities** (parameterized SQL, IDOR protection, token rotation, bcrypt, body limits). The most serious open issue for a **monitoring/decision-scoring** product is **trust boundary placement**: the server trusts client-submitted scores and assistant messages (OWASP A08/A04). Low-risk configuration and validation hardening from this audit closes several P1/P3 gaps without breaking the WebLLM browser inference flow.
