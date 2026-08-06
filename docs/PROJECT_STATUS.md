# Project status

**Date:** 2026-08-05  
**Prod model:** fine-tuned Gemma 2B **q4f16_2 embed-float** on volume llm-monitoring-app_mlc-model / gateway **:8080** (healthy).

## Checkpoint

- Diag :8088 six-Q passed on ackups/q4-embedfloat-weights → prod swap completed 2026-08-05.
- **Problem A (salad/stop): SOLVED** — factual 5/5 inish_reason=stop, no token salad.
- **Problem B (Go/15min token / su kaynama facts):** DeepKwiki context injection — compact `PROJECT_FACTS` in `frontend/src/lib/deepkwiki.ts`, pattern match, default ON in Chat. Eval: `python scripts/phase2_deepkwiki_eval.py`.
- Pre-swap backup: ackups/mlc-model-pre-q4f16_2-20260805-102842.tar.gz.

## Active path

| Step | Status |
|---|---|
| q4f16_2 embed-float artifact | Done (host + diag volume) |
| Prod backup + volume swap | Done |
| healthz + /v1/models | 
eady=true, id /app/model |
| Six-Q prod | Matches diag (az5-post-q4f16_2-prod.json) |
| q0f16 ~5GB path | Superseded for prod (diag optional) |

## Evidence

- HF merge OK; GGUF q8 OK; MLC q4f16_1/q4f32 FT salad → **fixed by float embed + q4f16_2**.
- mlc-server-spike image unchanged; --model-lib /app/model/gemma-cpu.so in compose.

## Success bar (deploy)

- Factual questions: clean stop, no salad = **PASS**
- Merhaba OOD = not a blocker; wrong project facts fixed by DeepKwiki inject

## Problem B verify

```powershell
curl.exe http://localhost:8080/healthz   # ready:true
node frontend/scripts/smoke-admin-deepkwiki.mjs
python scripts/phase2_deepkwiki_eval.py  # slow on CPU (~5–10 min/Q)
```

Chat UI: DeepKwiki on by default (`llmAdminStore`). Injected answers show `DeepKwiki: …` under assistant bubble.

Evidence: `backups/phase2-deepkwiki-eval.json` — **5/5 factual PASS** (Ankara, 4, 100°C, Go, 15 min) + Merhaba OOD `stop`.

## Verify locally

```powershell
curl.exe http://localhost:8080/healthz
python scripts/faz5_ask.py smoke-after-swap   # optional re-run
```

Frontend chat uses NEXT_PUBLIC_API_URL → same gateway when `npm run dev` on port 3000/3002.
