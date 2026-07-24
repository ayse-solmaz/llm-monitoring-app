# MLC-LLM CPU server spike

Isolated Docker spike to run **Gemma 2B** via MLC-LLM on **CPU only** (no GPU).
Uses pinned `mlc-ai-cpu` / `mlc-llm-cpu` 0.20.0 wheels — unpinned nightly builds are known to fail with libtvm symbol errors.

## Prerequisites

- Docker Desktop (Linux containers, `linux/amd64`)
- ~**15 GB free disk** for image layers, model weights, and compile artifacts
- Stable network (HuggingFace LFS download ~1.5 GB)

## Build

From the repo root:

```powershell
docker build --platform linux/amd64 -t mlc-server-spike ./mlc-server
```

Or from this directory:

```powershell
cd mlc-server
docker build --platform linux/amd64 -t mlc-server-spike .
```

**Expected build time (CPU-only host):** roughly **45–90 minutes**, mostly:

1. pip installs (~10–20 min)
2. `git lfs pull` for Gemma 2B (~5–15 min)
3. `mlc_llm compile … --device cpu` (~30–60+ min)

Watch the build log; the compile step is the slowest and has long quiet periods.

## Run

```powershell
docker run --rm -p 8000:8000 --name mlc-spike mlc-server-spike
```

Wait until the server logs show it is listening on port 8000. First inference may take extra time while weights load.

## Test — non-streaming

```powershell
curl.exe -s -X POST http://localhost:8000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{\"model\": \"gemma-2b-it\", \"messages\": [{\"role\": \"user\", \"content\": \"Say hello in one sentence.\"}], \"stream\": false, \"max_tokens\": 64}'
```

## Test — streaming

```powershell
curl.exe -N -X POST http://localhost:8000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{\"model\": \"gemma-2b-it\", \"messages\": [{\"role\": \"user\", \"content\": \"Count from 1 to 5.\"}], \"stream\": true, \"max_tokens\": 64}'
```

Streaming responses arrive as SSE `data: …` lines; the final line is `data: [DONE]`.

## Stop

```powershell
docker stop mlc-spike
```

(`--rm` removes the container on stop.)

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `ImportError` / missing `pytest` at startup | Runtime deps incomplete — `pytest` is required because `tvm.testing` imports it |
| `libtvm` / undefined symbol errors | Wrong MLC wheel versions — use the pinned 0.20.0 CPU wheels only |
| Compile OOM / killed | Docker memory limit too low — raise Docker Desktop memory to ≥8 GB |
| Slow first token | Normal on CPU; Gemma 2B q4f16_1 inference is not real-time without GPU |

## What this spike does **not** include

- No changes to `frontend/` or `backend/`
- No docker-compose wiring — run the container standalone
- No persistent volume; model is baked into the image at build time
