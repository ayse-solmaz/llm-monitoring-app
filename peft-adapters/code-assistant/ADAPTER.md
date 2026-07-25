# code-assistant adapter (soft PEFT)

**Id:** `code-assistant`  
**Mount path in container:** `/adapters/code-assistant`

## Purpose
Prefer short, code-focused answers with minimal prose.

## CPU demo
No LoRA weight files. Soft hot-swap via Admin → next Chat message.

## GPU / real LoRA
Place LoRA weights here when GPU MLC serve supports adapter load.
