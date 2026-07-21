# Raw LLM Monitoring & Decision Scoring App

Browser-side Gemma inference via MLC-LLM/WebLLM with live raw metrics and deterministic decision scoring. Sessions, messages, and scores are persisted to a Go backend and visualized on a monitoring dashboard.

## Live URLs

- **Frontend:** https://llm-monitoring-app.vercel.app

**Requirements:** Chrome or Edge 113+ (WebGPU). On the Render free tier, the first API request after idle may take 30–60 seconds to wake the service.

## Documentation

- [docs/API.md](docs/API.md) — architecture, endpoints, metrics & scoring
- [docs/MCP.md](docs/MCP.md) — MCP usage and local setup
- [docs/PERFORMANCE_REVIEW.md](docs/PERFORMANCE_REVIEW.md) — performance audit and fixes
- [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) — security audit and remediation status
