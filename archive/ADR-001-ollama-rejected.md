# ADR-001: Ollama tried and rejected

**Status:** Accepted  
**Date:** 2026-07-28

## Context

Intel Arc (Vulkan) looked like a faster demo path than Docker CPU MLC. We briefly explored Windows-native Ollama (`qwen2.5:1.5b`) wired through the KPI gateway.

## Decision

**Reject Ollama for the demo.** Keep the **MLC FINAL BOSS** story:

- Inference stays **MLC-LLM in Docker** (gateway → nginx → mlc).
- Go backend stays on Render for auth/sessions/scores only — **not** on the inference path.

## Consequences

- Archived: `docs/ARC_OLLAMA.md`, `docker-compose.ollama.yml`, `scripts/setup-arc-ollama.ps1` (this folder).
- Demo uses `scripts/demo-up.ps1` / `scripts/demo-down.ps1` and MLC on `:8080`.
