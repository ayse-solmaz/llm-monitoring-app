# Project wrap-up — how to demo & shut down

## What shipped

- **Cloud:** Frontend (Vercel) + Go API (Render) — auth, sessions, scores, dashboard
- **Local FINAL BOSS:** Docker MLC (CPU) → nginx → KPI gateway `:8080` → Chat/Admin on `:3002`
- **Admin / WebMCP / DeepKwiki / soft PEFT / Rich Result / Go internal MCP** — see [FINAL_BOSS_STATUS.md](./FINAL_BOSS_STATUS.md)

## Start (chat)

```powershell
cd C:\Users\aysnu\llm-monitoring-app
docker compose up -d --scale mlc=1
cd frontend
npm run dev -- -p 3002
```

- Chat: http://localhost:3002/chat → Connect → **one message at a time** (CPU is slow)
- Admin: http://localhost:3002/admin
- Gateway: http://localhost:8080/healthz — model id must be `/app/model`
- Grafana: http://localhost:3000 (admin/admin)

Frontend `.env.local`:

```
NEXT_PUBLIC_API_URL=https://llm-monitoring-api.onrender.com/api/v1
NEXT_PUBLIC_MLC_URL=http://localhost:8080
NEXT_PUBLIC_MLC_MODEL_ID=/app/model
```

## Scale demo (throughput, not single-request speed)

```powershell
docker compose up -d --scale mlc=3
```

## Stop

```powershell
docker compose down
```

## Public Chat via Cloudflare Tunnel (demo günü)

Sıra önemli — bu sırayla başlat:

1. `docker compose up -d --scale mlc=1` (repo kökünde)
2. `curl http://localhost:8080/healthz` ile doğrula (model: `/app/model`)
3. Tunnel (pencereyi **AÇIK BIRAK**):
   ```powershell
   & "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8080
   ```
4. Çıkan `https://*.trycloudflare.com` URL'ini kopyala (trailing slash yok)
5. Vercel → Project **llm-monitoring-app** → Settings → Environment Variables (Production):
   - `NEXT_PUBLIC_API_URL` = `https://llm-monitoring-api.onrender.com/api/v1`
   - `NEXT_PUBLIC_MLC_URL` = `https://….trycloudflare.com` (tunnel URL)
   - `NEXT_PUBLIC_MLC_MODEL_ID` = `/app/model`
6. **Redeploy** (Deployments → … → Redeploy). `NEXT_PUBLIC_*` build-time — env yetmez.
7. Incognito: Vercel URL → login → Chat → Connect → **tek** kısa mesaj; bitmeden ikinci yok.

Production site (team): `https://llm-monitoring-app-098765467890.vercel.app`

### PC kapanırsa / uyursa Chat ölür

- `powercfg /change standby-timeout-ac 0`
- Docker Desktop + cloudflared penceresi açık
- Laptop: güç kablosu takılı

### Tunnel URL değişirse

1. Yeni URL → Vercel `NEXT_PUBLIC_MLC_URL`
2. Redeploy
3. 1–2 dk bekle, tekrar test

### Demo sonrası

```powershell
docker compose down
```

cloudflared penceresinde Ctrl+C.

### Güvenlik

Quick tunnel açıkken gateway URL'ini bilen herkes `/v1/*` çağırabilir (DB yok). Demo bitince tunnel kapat.

## Do not

- Rebuild `mlc-server-spike` unless necessary (~1h+)
- Send overlapping Chat requests on CPU
- Expect GPU-speed answers on CPU
- Leave the Cloudflare tunnel running after the demo
