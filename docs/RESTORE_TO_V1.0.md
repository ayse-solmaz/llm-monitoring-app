# Restore to v1.0 working state

**Tag:** `v1.0-working`  
**Commit:** `1730580` (`173058051380716cbd19936f395db5e68b091c3d`)  
**Meaning:** q4f16_2 FT Gemma in prod (Problem A solved), DeepKwiki facts (Problem B solved), local self-contained stack.

Use this when a browser/WebLLM experiment (or any later work) breaks the tree and you need the known-good state back.

---

## What was frozen

| Layer | Location |
|-------|----------|
| Git tag | `v1.0-working` (annotated) |
| Git branch | `backup/v1.0-working` |
| Offline folder | `C:\Users\aysnu\llm-monitoring-app-BACKUP-v1.0\` |
| Working model (host) | `backups/q4-embedfloat-weights/` |
| Working model (HF) | https://huggingface.co/ayse-solmaz/gemma-2b-it-tr-q4f16-2 (private) |
| Pre-swap rollback tar | `backups/mlc-model-pre-q4f16_2-20260805-102842.tar.gz` (~1.14 GB) |
| Prod volume snapshot | `backups/mlc-model-v1.0-working-20260806-094314.tar.gz` (~1.67 GB) |

Also kept on HF (related, not the prod q4f16_2):  
`ayse-solmaz/gemma-2b-it-tr-q0f16`, `…-q4f32`, `…-tr-lora`, `…-tr-mlc`.

---

## Path A — Git only (code + docs; not Docker weights)

```powershell
cd C:\Users\aysnu\llm-monitoring-app
git fetch origin
git checkout v1.0-working
# or: git checkout backup/v1.0-working
# or reset main (destructive — only if you intend to discard later commits):
#   git checkout main
#   git reset --hard v1.0-working
```

Then reseed the MLC volume from Path C or D if the running model was changed.

---

## Path B — Full folder copy (offline machine / total disaster)

```powershell
# Stop anything using the live folder first
docker compose -f C:\Users\aysnu\llm-monitoring-app\docker-compose.yml down

# Replace live tree with the backup (keeps a .OLD copy of the broken tree)
Rename-Item C:\Users\aysnu\llm-monitoring-app C:\Users\aysnu\llm-monitoring-app-BROKEN
Copy-Item -Recurse C:\Users\aysnu\llm-monitoring-app-BACKUP-v1.0 C:\Users\aysnu\llm-monitoring-app

cd C:\Users\aysnu\llm-monitoring-app
docker compose up -d --scale mlc=1
# Wait until:
curl.exe http://localhost:8080/healthz
# expect "ready":true
```

The folder backup includes `.git`, `backups/q4-embedfloat-weights/`, and the rollback / v1.0 volume tars. It excludes `node_modules`, `.next`, `vendor/`, and other multi-GB experimental weight trees (q0f16 / q4f32 / HF base copies).

```powershell
cd frontend
npm install
npm run dev -- -p 3002
```

---

## Path C — Restore prod Docker volume from v1.0 snapshot tar

Use the **v1.0-working** volume tar (not the older pre-q4f16_2 tar unless you want base q4f16_1).

```powershell
cd C:\Users\aysnu\llm-monitoring-app
docker compose stop mlc

# v1.0 snapshot (2026-08-06)
$tarName = "mlc-model-v1.0-working-20260806-094314.tar.gz"
Write-Host "Restoring from backups\$tarName"

docker run --rm `
  -v llm-monitoring-app_mlc-model:/model `
  -v C:\Users\aysnu\llm-monitoring-app\backups:/backup:ro `
  alpine sh -c "rm -rf /model/*; tar xzf /backup/$tarName -C /model; ls -la /model; file /model/gemma-cpu.so"

docker compose start mlc
# If gateway stuck busy/ready:false:
docker compose restart gateway

Start-Sleep 60
curl.exe http://localhost:8080/healthz
# expect ready:true, then smoke:
python scripts/faz5_ask.py restore-v1.0-check
```

Verify config: `quantization: q4f16_2`, `stop_token_ids: [1, 107]`.

---

## Path D — Reseed volume from `q4-embedfloat-weights/` (same bytes as HF)

If the volume tar is missing but host/HF artifact exists:

```powershell
docker compose stop mlc

docker run --rm `
  -v llm-monitoring-app_mlc-model:/model `
  -v C:\Users\aysnu\llm-monitoring-app\backups\q4-embedfloat-weights:/new:ro `
  alpine sh -c "
    rm -f /model/params_shard_*.bin
    rm -f /model/tensor-cache.json /model/ndarray-cache.json
    rm -f /model/gemma-cpu.so /model/mlc-chat-config.json
    cp /new/params_shard_*.bin /model/
    cp /new/gemma-cpu.so /model/
    cp /new/mlc-chat-config.json /model/
    cp /new/tensor-cache.json /model/tensor-cache.json
    cp /new/tensor-cache.json /model/ndarray-cache.json
    ls -la /model/
  "

docker compose start mlc
docker compose restart gateway
```

From HF (if local weights lost):

```powershell
hf download ayse-solmaz/gemma-2b-it-tr-q4f16-2 --local-dir backups/q4-embedfloat-weights
# then Path D copy into volume
```

---

## Path E — Roll back to **pre**-FT base (q4f16_1) only

Only if you need the state **before** the q4f16_2 promote:

```powershell
docker compose stop mlc
docker run --rm `
  -v llm-monitoring-app_mlc-model:/model `
  -v C:\Users\aysnu\llm-monitoring-app\backups:/backup:ro `
  alpine sh -c "rm -rf /model/*; tar xzf /backup/mlc-model-pre-q4f16_2-20260805-102842.tar.gz -C /model; ls -la /model/"
docker compose start mlc
```

This is **not** v1.0 FT — it is the emergency base-model rollback.

---

## Quick health checklist after restore

1. `git rev-parse HEAD` → should be `1730580…` if on the tag  
2. `curl.exe http://localhost:8080/healthz` → `"ready":true`  
3. Chat: “Türkiye'nin başkenti nedir?” → Ankara, `finish_reason=stop`  
4. With DeepKwiki ON: su → 100°C, backend → Go, token → 15 dakika  
5. Do **not** rebuild `mlc-server-spike` unless you know you need to  

---

## Notes

- Prod inference stays **local** (Phase 2 decision A). Vercel hosts frontend only.  
- Gateway `busy` / `ready:false`: `docker compose restart mlc` then `gateway` (volume untouched).  
- Upstream MLC issue draft: `docs/MLC_UPSTREAM_ISSUE_BODY.md` (post-project).  
