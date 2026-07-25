# PEFT / LoRA adapters (FINAL BOSS)

Docker Compose mounts this directory into each `mlc` container at `/adapters` (read-only).

## Demo adapters

| Folder id | Mode | Purpose |
| --- | --- | --- |
| `deepkwiki` | Soft (CPU) | Docs / wiki tone — see `deepkwiki/ADAPTER.md` |
| `code-assistant` | Soft (CPU) | Concise code help — see `code-assistant/ADAPTER.md` |

Admin → select adapter → **next Chat message** applies style (soft hot-swap). Real LoRA weights belong here when using GPU compose overlay.
