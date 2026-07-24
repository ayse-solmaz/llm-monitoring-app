# MLC Scaling Report

CPU-only horizontal scaling for Gemma 2B via MLC-LLM, fronted by a **FastAPI KPI gateway** + nginx `least_conn`, observed with Prometheus + cAdvisor + Grafana.

**Host:** 16 logical cores, Intel integrated graphics (no discrete GPU).  
**Image:** pre-built `mlc-server-spike` (~98 min first build — not rebuilt by compose).  
**Per-replica limits:** 4 CPU, 6G RAM (constant across scale).  
**Benchmark date:** 2026-07-24 (load tests); gateway KPI layer added after.

---

## 1. Executive Summary

Horizontal scaling **works** on this stack: nginx `least_conn` spreads concurrent chat completions across MLC replicas, and wall-clock throughput rises when going from 1 → 3 replicas. A FastAPI **gateway** now sits in front of nginx so TTFT, tokens/sec, inflight, and E2E latency are exported on `/metrics` for Prometheus (pull model).

| Metric | 1 replica | 3 replicas | Change |
|--------|-----------|------------|--------|
| Wall time (6 requests) | **1061.1 s** | **465.0 s** | **−56%** |
| Throughput | **0.005 req/s** | **0.013 req/s** | **+160% (~2.6×)** |
| Latency p50 | 155 s | 169 s | +9% (worse under contention) |
| Latency p95 | 165 s | 287 s | +74% (worse under contention) |

**Takeaways:**

1. **Throughput scales** — more replicas finish a fixed batch of work faster (~2.6× req/s with 3× replicas).
2. **Per-request latency does not improve** — and can worsen under concurrent load because replicas share a CPU-bound host (3 × 4 cores = 12 of 16 logical cores).
3. **Cold start is real but short** once the image exists — new replicas reached `healthy` in ~20–25 s (weights baked into the image).
4. **CPU ≠ GPU** — single-request generation stays on the order of **2–5 minutes** for `max_tokens=32` on this host; GPU deployments would target sub-second to few-second latency.

---

## 2. Architecture

```mermaid
flowchart LR
  Client["Client / loadtest / Next.js Chat"]
  GW["mlc-gateway :8080<br/>FastAPI · KPI /metrics"]
  Nginx["nginx<br/>least_conn · streaming"]
  M1["mlc replica 1"]
  M2["mlc replica 2"]
  M3["mlc replica 3"]
  Cad["cAdvisor :8081"]
  Prom["Prometheus :9090<br/>scrape 5s"]
  Graf["Grafana :3000"]

  Client --> GW
  GW --> Nginx
  Nginx --> M1
  Nginx --> M2
  Nginx --> M3
  GW -.->|pull /metrics| Prom
  Cad --> Prom
  Prom --> Graf
```

| Component | Role |
|-----------|------|
| **gateway** | Public entry (`:8080`); forces `stream=true`; measures TTFT / E2E / tok/s / inflight; `/metrics` |
| **nginx** | Internal LB only; Docker DNS + `least_conn`; 300s timeouts; streaming |
| **mlc** | OpenAI-compatible `/v1/chat/completions`; CPU Gemma 2B `q4f16_1` |
| **cAdvisor** | Per-container CPU / memory / network |
| **Prometheus** | Scrapes **gateway** + **cAdvisor** every 5 s (pull — nothing pushes to Grafana) |
| **Grafana** | Dashboard with RPS, p95 latency, p95 TTFT, inflight, tok/s, error rate, MLC count, CPU |

### LLM KPIs published by the gateway

| Metric | Type | Meaning |
|--------|------|---------|
| `llm_requests_total{status}` | Counter | Requests (ok/error) |
| `llm_output_tokens_total` | Counter | Completion tokens |
| `llm_requests_inflight` | Gauge | Saturation / concurrency |
| `llm_request_duration_seconds` | Histogram | End-to-end latency |
| `llm_ttft_seconds` | Histogram | Time to first content token |
| `llm_tokens_per_second` | Histogram | Tokens / decode seconds after TTFT |

---

## 3. Methodology

### Why load parameters were scaled down

Assignment-style **200 requests / 20 concurrent** is unrealistic on CPU:

- Measured generation ≈ **130–290 s** per request (`max_tokens=32`).
- 200 × ~150 s serial ≈ **8+ hours**; 20 concurrent would queue and 502 under nginx timeouts.

**Chosen suite:** `scripts/loadtest.ps1` with **6 total requests**, concurrency = replica count (1 or 3). Same prompt shape, `max_tokens=32`, via `http://localhost:8080`.

Raw outputs: [`evidence/loadtest-1replica.txt`](evidence/loadtest-1replica.txt), [`evidence/loadtest-3replica.txt`](evidence/loadtest-3replica.txt).

### Test setup

```powershell
docker compose up -d --scale mlc=1   # then loadtest -Total 6 -Concurrent 1
docker compose up -d --scale mlc=3   # wait healthy, then -Total 6 -Concurrent 3
```

Host: Windows + Docker Desktop WSL2, 16 logical cores, cpus=4.0 / mem=6G per replica.

---

## 4. Findings

### 4.1 One-replica benchmark

| Metric | Value |
|--------|-------|
| Total wall time | **1061.1 s** |
| Successful | 5 / 6 (1× **504** — nginx `proxy_read_timeout` 300s edge case) |
| Throughput | **0.005 req/s** |
| Latency avg | **151499 ms** (~151.5 s) |
| Latency p50 | **155089 ms** |
| Latency p95 | **164528 ms** |

### 4.2 Three-replica benchmark

| Metric | Value |
|--------|-------|
| Total wall time | **465.0 s** |
| Successful | **6 / 6** |
| Throughput | **0.013 req/s** |
| Latency avg | **206674 ms** (~206.7 s) |
| Latency p50 | **169339 ms** |
| Latency p95 | **286552 ms** |

### 4.3 Delta table

| Metric | 1 → 3 | Interpretation |
|--------|-------|----------------|
| Wall time | **−56%** | Batch finishes sooner |
| Throughput | **+160% (2.6×)** | Near-linear concurrent capacity |
| p50 latency | **+9%** | Shared CPU contention |
| p95 latency | **+74%** | Tail hurt when 3 replicas generate at once |

Load balancing (3 concurrent → 3 distinct upstreams), from nginx logs during the 3-replica run:

```
upstream=172.18.0.8:8000  request_time=283.877
upstream=172.18.0.7:8000  request_time=286.272
upstream=172.18.0.2:8000  request_time=168.600
```

Earlier proof file: [`evidence/nginx-access-1vs3.txt`](evidence/nginx-access-1vs3.txt).

### 4.4 Cold start

Scaling `mlc=1` → `mlc=3` (2026-07-24). New containers: `health: starting` → `healthy` in **~23 seconds** (weights already in image).

| Time | mlc-2 / mlc-3 |
|------|----------------|
| +5 s | health: starting |
| +11 s | health: starting |
| +17 s | health: starting |
| +23 s | **healthy** |

Full poll log: [`evidence/cold-start-scale3.txt`](evidence/cold-start-scale3.txt).

Until healthy, nginx can return 502/503 — always wait for `docker compose ps` healthy before demos/load tests.

---

## 5. Theory (no extra code — exam / report topics)

### 5.1 Autoscaling: threshold, cooldown, flapping

- **Scale up** when a signal crosses a threshold (CPU, inflight requests, queue depth).
- **Cooldown / hysteresis** — wait N seconds before acting again so one spike does not create 10 pods.
- **Flapping** — metrics oscillating around the threshold cause endless create/destroy; hysteresis + separate scale-down threshold fix this.
- This repo demos scale **manually** (`--scale mlc=N`). Cloud automation is HPA/KEDA (below).

### 5.2 API Gateway vs Load Balancer

| | Load balancer | API Gateway |
|--|---------------|-------------|
| Job | Distribute traffic | Auth, rate limit, routing, often LB too |
| Here | nginx `least_conn` | FastAPI gateway (KPI + CORS + stream policy) |

### 5.3 Cold start

New replica must load weights (~1.3–1.8 GB) and pass healthchecks before it should receive traffic. Scaling up and immediately load-testing yields 502s. Always wait for `healthy`. Shared **named volumes** for weights reduce duplicate downloads; this spike still bakes weights into the image (trade-off: simpler CPU demo, larger image).

### 5.4 How MLC splits / runs the model

- **Quantization `q4f16_1`:** weights ~4-bit, activations float16 — smaller RAM, faster CPU/GPU path than full precision.
- **Tensor / pipeline parallelism:** split layers or tensors across GPUs (not used here — single CPU device).
- **Continuous batching:** one engine serves many in-flight requests by batching decode steps; raises single-container concurrency until KV-cache / CPU saturates. Horizontal replicas add *more* engines when one is saturated.

### 5.5 Logs vs metrics vs traces

| Signal | Answers | This project |
|--------|---------|--------------|
| Metrics | How many / how fast / how wrong | Gateway + cAdvisor → Prometheus → Grafana |
| Logs | Why (text events) | Docker / nginx stdout (not centralized) |
| Traces | Where time went across services | Not implemented |

### 5.6 Cloud path (if this left the laptop)

- **Deployment** — ReplicaSet of MLC pods + gateway Deployment  
- **HPA** — scale MLC on CPU or custom metric (`llm_requests_inflight`)  
- **KEDA** — scale on queue length / Prometheus query  
- **GPU node pool** — one replica ≈ one GPU for real throughput; multi-replica on one GPU mostly buys concurrency, not 3× speed  

### 5.7 Shared volumes vs “new baby” containers

Each scaled container is a new process (“born empty”). If every replica carried its own copy of weights/DB, you waste disk and cold-start longer. Shared **volume** = same files, many readers. Postgres stays a separate service; MLC replicas stay **stateless** request handlers.

---

## 6. Limitations & Future Work

- **CPU bottleneck** — scaling adds parallel slots, not faster tokens.
- **No MLC Prometheus metrics** — need sidecar or nginx log exporters for TTFT histograms.
- **nginx 300s timeout** — one 504 on the 1-replica run; raise timeout or lower `max_tokens` for demos.
- **Port clash** — Grafana and Next.js both want `:3000`; API vs nginx both want `:8080` unless API uses `PORT=8081`.
- **Future:** GPU (`cu121`) images, better quantization/scheduling, streaming-first UX, optional Redis for multi-node LB state.

---

## 7. Conclusion

Horizontal scaling with **nginx `least_conn` + N MLC CPU replicas** is proven: **~2.6× throughput** and **~56% shorter** batch wall time from 1 → 3 replicas, with multi-IP `upstream_addr` evidence.

The remaining ceiling is **hardware**. For interactive product UX, prefer **GPU MLC** or keep **browser WebLLM** (`/spike`). Use this CPU stack for offline scaling demos, observability practice, and cost modeling without a GPU.

**GPU deployment recommendations:** NVIDIA Container Toolkit + `mlc-llm` CUDA wheels; keep nginx `least_conn` and Prometheus/cAdvisor; expect order-of-magnitude lower latency and higher tokens/sec per replica.

---

## Operations quick reference

```powershell
cd C:\Users\aysnu\llm-monitoring-app
docker compose up -d --scale mlc=3
.\scripts\loadtest.ps1 -Total 6 -Concurrent 3
curl.exe -s http://localhost:8080/metrics | Select-String "llm_"
docker compose logs nginx --no-color | Select-String "upstream="
docker compose down
```

| Service | URL |
|---------|-----|
| Chat via **gateway** | http://localhost:8080/v1/chat/completions |
| Gateway `/metrics` | http://localhost:8080/metrics |
| Prometheus targets | http://localhost:9090/targets |
| Grafana | http://localhost:3000 (admin / admin) |
| Dashboard | http://localhost:3000/d/mlc-scaling-cadvisor |
