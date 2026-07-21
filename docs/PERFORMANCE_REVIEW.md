# Go Backend Performance Review

## Implemented now vs deferred

### Implemented in this commit (P0 + P1 quick wins)

| # | Item | Location |
|---|------|----------|
| 1 | Postgres connection pool (`MaxOpenConns=25`, `MaxIdleConns=10`, `ConnMaxLifetime=30m`, `ConnMaxIdleTime=5m`) | `internal/database/database.go` |
| 2 | Explicit `http.Server` timeouts (`ReadTimeout=10s`, `WriteTimeout=30s`, `IdleTimeout=120s`) | `cmd/server/main.go` |
| 3 | GORM context propagation via `withCtx(c, h.db)` on all handler DB calls and transactions | `internal/handlers/context.go`, `auth.go`, `llm.go` |
| 4 | Rate limiter idle entry eviction (10m ticker, 30m TTL) | `internal/middleware/ratelimit.go` |
| 5 | Composite DB indexes (`idx_messages_session_role`, `idx_sessions_user_created`, `idx_refresh_tokens_user_revoked`) | `internal/database/database.go` |
| 6 | 1MB body size limit on `/llm` route group | `internal/router/router.go` |
| 7 | JWT/refresh token generation moved outside DB transactions in `issueTokens` and `Refresh` | `internal/handlers/auth.go` |

### Consciously deferred (MVP scope / future work)

- `gin.H` → typed DTO structs (GC allocation reduction)
- `GetSession` pagination / bounded message loading
- bcrypt worker pool / bounded CPU for auth
- Rate limiter mutex sharding or Redis-backed distributed limiting
- Repository interface extraction and read-replica routing
- Dedicated migration tooling (replace startup `AutoMigrate` in production)
- `ListSessions` single-query pagination, `CreateScore` upsert consolidation
- `Me` endpoint user lookup cache

---

## Full analysis

**Scope:** `backend/` — Gin + GORM + PostgreSQL/SQLite, synchronous request-per-goroutine model.

**Overall:** The service is appropriate for small-to-medium monitoring API traffic. Under high load, bottlenecks concentrate in **I/O propagation**, **connection pool management**, **heap allocation from response maps**, and **rate limiter / auth contention**.

---

## 1. Bellek Yönetimi ve GC Baskısı

### 1.1 Her response için `gin.H` (`map[string]any`) tahsisi

- **Sorun:** `publicSession`, `publicMessage`, `publicScore` and list endpoints allocate new `gin.H` maps and box every field into `interface{}` (`handlers/llm.go`).
- **Mimari Etki:** Session detail with many messages causes O(n) heap allocations per request. High RPS increases GC pause frequency and P99 latency.
- **Çözüm Önerisi:** Define response DTO structs with JSON tags; serialize directly. Pre-size slices: `make([]MessageResponse, 0, len(s.Messages))`.

### 1.2 `GetSession` — unbounded message + content loading

- **Sorun:** `Preload("Messages").Preload("Messages.Score")` loads the entire session graph including large `Content` strings.
- **Mimari Etki:** Long multi-turn sessions can cause heap spikes, GC thrashing, and OOM risk. Memory pressure scales with concurrent requests.
- **Çözüm Önerisi:** Cursor-based message pagination; metadata + last N messages by default.

### 1.3 `roundFloat` heap escape

- **Sorun:** Returns `&rounded` pointer on each call (`llm.go`).
- **Mimari Etki:** Small but continuous allocations on summary endpoints under load.
- **Çözüm Önerisi:** Return `(float64, bool)` or use optional struct fields with `omitempty`.

### 1.4 bcrypt (cost=12) on request path

- **Sorun:** Password hash/verify runs synchronously in the request goroutine (~250–400ms CPU-bound).
- **Mimari Etki:** Login/register storms block Gin workers; throughput capped by CPU cores.
- **Çözüm Önerisi:** Bounded worker pool for bcrypt; dedicated auth rate limits.

### 1.5 Rate limiter map growth *(partially addressed)*

- **Sorun:** ~~Unbounded `map[string]*ipLimiter` without eviction~~ — **now mitigated** with 30-minute idle cleanup.
- **Mimari Etki:** At very large unique-IP counts, map still grows between cleanup ticks; distributed deployments need shared limiter state.
- **Çözüm Önerisi:** Redis sliding-window limiter for horizontal scale.

---

## 2. Eşzamanlılık ve Senkronizasyon

### 2.1 Global mutex on rate limiter

- **Sorun:** Every auth request acquires `sync.Mutex` in `getLimiter`.
- **Mimari Etki:** Auth P99 latency serializes under contention on multi-core hosts.
- **Çözüm Önerisi:** Sharded locks (`256` shards + `xxhash`) or `sync.Map` for read-heavy paths.

### 2.2 HTTP server timeouts *(implemented)*

- **Sorun:** ~~`r.Run()` with no explicit timeouts~~ — **fixed** with `ReadTimeout`, `WriteTimeout`, `IdleTimeout`.
- **Mimari Etki:** Slow clients can no longer hold connections indefinitely.

### 2.3 Context propagation *(implemented)*

- **Sorun:** ~~GORM calls without `WithContext`~~ — **fixed** via `withCtx(c, h.db)` across handlers.
- **Mimari Etki:** Client disconnect can now cancel in-flight DB work when the driver supports it.

### 2.4 Crypto inside DB transactions *(implemented)*

- **Sorun:** ~~JWT generation inside transactions~~ — **fixed** in `issueTokens` and `Refresh`.
- **Mimari Etki:** Shorter transaction hold times on `refresh_tokens`; reduced lock contention.

---

## 3. I/O, Ağ ve Veritabanı Darboğazları

### 3.1 Connection pool *(implemented for Postgres)*

- **Sorun:** ~~No `SetMaxOpenConns` / idle tuning~~ — **fixed** for Postgres connections.
- **Mimari Etki:** Predictable connection usage vs PostgreSQL `max_connections`; reduced connection churn.

### 3.2 `ListSessions` — Count + Find (two round trips)

- **Sorun:** Separate `Count` and `Find` queries per page request.
- **Mimari Etki:** 2× DB latency on paginated dashboard polling.
- **Çözüm Önerisi:** Window function single query or cursor pagination without total count.

### 3.3 `CreateScore` — three sequential queries

- **Sorun:** Message lookup → existence check → insert.
- **Mimari Etki:** 3× latency per score POST during chat streaming.
- **Çözüm Önerisi:** Unique constraint on `message_id` + single insert with conflict handling.

### 3.4 Summary query indexes *(implemented)*

- **Sorun:** ~~Missing composite indexes for user-scoped aggregates~~ — **fixed** with three indexes after migrate.
- **Mimari Etki:** Faster `MetricsSummary`, `ScoresSummary`, session listing, and refresh-token revocation.

### 3.5 `AutoMigrate` on every startup

- **Sorun:** Schema migration runs on each process start.
- **Mimari Etki:** Deploy-time schema locks; multi-instance migration races.
- **Çözüm Önerisi:** CI/CD migration step (`golang-migrate`, `goose`); app only pings DB.

### 3.6 LLM body size limit *(implemented)*

- **Sorun:** ~~No body limit on LLM routes~~ — **fixed** with 1MB `MaxBodySize` middleware.
- **Mimari Etki:** Mitigates large payload DoS on message creation.

### 3.7 `Me` — redundant DB round-trip

- **Sorun:** JWT carries `userID` but `currentUser` always `SELECT`s full user row.
- **Mimari Etki:** Extra DB load on profile endpoints at high RPS.
- **Çözüm Önerisi:** Short-TTL cache or minimal claims in JWT.

---

## 4. Mimari Kuplaj ve Verimlilik

### 4.1 Handler → `*gorm.DB` direct coupling

- **Sorun:** Handlers depend on concrete GORM type; no consumer-defined interfaces.
- **Mimari Etki:** Hard to swap in raw SQL, read replicas, or batch optimizations without handler churn.
- **Çözüm Önerisi:** Thin `SessionStore` / `AuthStore` interfaces implemented in `internal/store/postgres`.

### 4.2 Presentation logic mixed with handlers (`gin.H`)

- **Sorun:** Serialization format lives inside handler functions.
- **Mimari Etki:** Cannot change allocation patterns or add alternate encodings without refactoring handlers.
- **Çözüm Önerisi:** `internal/api/dto` package with explicit mapping.

### 4.3 Global singleton rate limiter

- **Sorun:** Package-level `authRateLimiter`; not injectable; per-instance limits when horizontally scaled.
- **Mimari Etki:** Effective rate limit = N × configured limit across N instances.
- **Çözüm Önerisi:** Inject limiter from `router.New`; Redis for production.

### 4.4 GORM reflection overhead

- **Sorun:** All persistence through GORM reflection pipeline.
- **Mimari Etki:** ~15–30% CPU overhead on hot paths vs hand-written SQL (workload-dependent).
- **Çözüm Önerisi:** `sqlc` / `pgxpool` for message insert and session list; keep GORM for admin paths.

### 4.5 `isDuplicateKeyError` string matching

- **Sorun:** `strings.Contains(err.Error(), "duplicate key")` for constraint detection.
- **Mimari Etki:** Misclassification can cause wrong HTTP status and client retry amplification.
- **Çözüm Önerisi:** Typed errors via `errors.As` with `pgconn.PgError` code `23505`.

---

## Priority matrix (remaining)

| Priority | Topic | Impact |
|----------|-------|--------|
| **P1** | GetSession pagination | Heap spike, OOM |
| **P1** | gin.H → struct DTO | GC pressure |
| **P2** | bcrypt worker pool | Auth throughput |
| **P2** | Mutex sharding / Redis rate limit | Auth P99, horizontal scale |
| **P3** | Repository interfaces | Long-term optimization path |

---

## Conclusion

P0 and selected P1 items are now implemented. The backend is better protected against connection exhaustion, hung clients, unbounded rate-limiter memory growth, missing query indexes, and unnecessarily long transactions. Remaining items are documented for post-MVP hardening when traffic or SLO requirements increase.

Operational recommendation: export `sql.DB.Stats()` and enable `pprof` in staging to validate pool sizing and GC under load tests.
