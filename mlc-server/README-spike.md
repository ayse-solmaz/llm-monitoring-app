# MLC-LLM CPU server spike

Isolated Docker spike to run **Gemma 2B** via MLC-LLM on **CPU only** (no GPU).
Uses pinned `mlc-ai-cpu` / `mlc-llm-cpu` 0.20.0 wheels — unpinned nightly builds are known to fail with libtvm symbol errors.

## Prefer the existing image

If `docker images` already shows `mlc-server-spike:latest`, **do not rebuild** (~45–90 min). Compose uses that tag with `pull_policy: never`.

## Prerequisites

- Docker Desktop (Linux containers, `linux/amd64`)
- ~**15 GB free disk** for image layers, model weights, and compile artifacts
- Stable network (HuggingFace LFS download ~1.5 GB) — only if rebuilding

## Build (only if image missing)

```powershell
docker build --platform linux/amd64 -t mlc-server-spike ./mlc-server
```

## Run

```powershell
cd C:\Users\aysnu\llm-monitoring-app
docker compose up -d --scale mlc=1
curl.exe http://localhost:8080/v1/models
```

Model id is typically `/app/model`. Soft PEFT (Admin) only — no real LoRA in this spike.

## Stop

```powershell
docker compose down
```
