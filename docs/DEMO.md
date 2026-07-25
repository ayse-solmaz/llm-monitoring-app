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

## Do not

- Rebuild `mlc-server-spike` unless necessary (~1h+)
- Send overlapping Chat requests on CPU
- Expect GPU-speed answers on CPU
