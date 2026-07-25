# deepkwiki adapter (soft PEFT)

**Id:** `deepkwiki`  
**Mount path in container:** `/adapters/deepkwiki`

## Purpose
Bias answers toward this project's docs / DeepKwiki facts (gateway, scaling, MLC, auth).

## CPU demo
No LoRA weight files. Admin soft hot-swap injects style via WebMCP + Go `HandleMCPRequest` adapter hint.

## GPU / real LoRA
Drop compiled LoRA artifacts here when using `docker compose -f docker-compose.yml -f docker-compose.gpu.yml`.
