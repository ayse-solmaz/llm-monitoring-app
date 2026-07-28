# Intel Arc path — system profile & model choice

> **Archived.** Ollama was tried and rejected to keep the MLC FINAL BOSS demo story.  
> See [ADR-001-ollama-rejected.md](../ADR-001-ollama-rejected.md).

## Your machine (checked 2026-07-28)

| Item | Value |
|------|--------|
| GPU | **Intel Arc 140T (16GB)** — OK |
| NVIDIA / CUDA | **None** (`nvidia-smi` missing) |
| CPU | Core Ultra 9 285H (16 threads) |
| RAM | ~31 GB (Docker + browsers use a lot) |
| Disk C | ~560 GB free |
| Docker | Desktop / WSL2 — **no Intel GPU passthrough** (`/dev/dri` empty in Ubuntu WSL) |
| Current MLC | Docker **CPU** Gemma 2B (~2–5 min/reply) |

**Conclusion:** Arc is strong enough for 0.5B–7B quantized models, but **not reachable from Docker**. Fast path = **Windows-native Ollama** (Vulkan → Arc) + keep KPI gateway in Docker pointed at the host.

## Chosen model

| Role | Model | Why |
|------|--------|-----|
| **Primary (recommended)** | `qwen2.5:1.5b` | Fits Arc easily, much faster than CPU Gemma 2B, decent quality for demo |
| Optional faster | `qwen2.5:0.5b` | Lowest latency |
| Optional nicer | `qwen2.5:3b` or `gemma2:2b` | Still fine on 16GB Arc |

Soft PEFT (Admin adapters/prompts) stays as-is. Real LoRA weights are still out of scope.

## Architecture

```
Browser :3002 → /api/mlc → Docker gateway :8080 → host.docker.internal:11434 (Ollama/Arc)
                                              ↘ JWT → Render API (unchanged)
```

CPU `mlc` container can stay stopped to free RAM.

## One-time setup

1. Install [Ollama](https://ollama.com/download/windows) (or winget: `winget install Ollama.Ollama`).
2. Pull model:

```powershell
ollama pull qwen2.5:1.5b
ollama run qwen2.5:1.5b "Hi"
```

3. Point gateway at Ollama (repo compose already supports this via env):

```powershell
cd C:\Users\aysnu\llm-monitoring-app
$env:MLC_UPSTREAM = "http://host.docker.internal:11434"
docker compose up -d gateway nginx prometheus grafana cadvisor
# optional: stop CPU mlc to free RAM
docker compose stop mlc
```

4. Frontend:

```powershell
cd frontend
# .env.local already uses MLC_UPSTREAM for Next proxy when set;
# for local Next, also set:
# MLC_UPSTREAM=http://127.0.0.1:11434
npm run dev -- -p 3002
```

Chat → Connect → short message. Expect **seconds**, not minutes, when Arc is used.
