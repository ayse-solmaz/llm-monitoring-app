from pathlib import Path

path = Path("docs/MLC_DEBUG_PLAN.md")
text = path.read_text(encoding="utf-8-sig")
text = text.replace(chr(12), "f").replace(chr(8), "b")

def L(bs: bytes) -> str:
    return bs.decode("latin-1")

repls = [
    (L(bytes([0xC4, 0x9F])), "\u011f"),
    (L(bytes([0xC5, 0x9F])), "\u015f"),
    (L(bytes([0xC4, 0xB1])), "\u0131"),
    (L(bytes([0xC4, 0xB0])), "\u0130"),
    (L(bytes([0xC3, 0xBC])), "\u00fc"),
    (L(bytes([0xC3, 0xB6])), "\u00f6"),
    (L(bytes([0xC3, 0xA7])), "\u00e7"),
    (L(bytes([0xC3, 0x9C])), "\u00dc"),
    (L(bytes([0xC3, 0x96])), "\u00d6"),
    (L(bytes([0xC3, 0x87])), "\u00c7"),
    (L(bytes([0xC2, 0xB7])), "\u00b7"),
    ("\xc4\u0178", "\u011f"),
    ("\xc5\u0178", "\u015f"),
]
for a, b in repls:
    text = text.replace(a, b)

start = text.find("## Phase 1 follow-up")
phase = (
    "## Phase 1 follow-up --- lm_head / tied-embed hunt (2026-08-05)\n\n"
    "See **[MLC_Q4_LMHEAD_HUNT.md](./MLC_Q4_LMHEAD_HUNT.md)** (artifacts + next experiment) "
    "and paste-ready **[MLC_UPSTREAM_ISSUE_DRAFT.md](./MLC_UPSTREAM_ISSUE_DRAFT.md)**.\n\n"
    "**One-liner for issue trackers:** Gemma-2B-IT q4 CPU raw decode logits suppress token 107 "
    "by ~1.8 vs q0 at step 4 (sentra wins); offline dequant+matmul on same hidden does **not** "
    "reproduce -1.8 -> suspect compiled `fused_dequantize_NT_matmul{4,9,14}` on tied "
    "`model.embed_tokens` and/or activation drift (sampler OK; `logit_bias[107]=+2` restores stop).\n\n"
    "Offline isolate: `python scripts/q4_lmhead_isolate.py` -> `backups/q4-lmhead-isolate.json` "
    "(`CONCLUSION: KERNEL_OR_ACTIVATION_PATH`).\n\n"
)
yasak = (
    "## Yasak\n\n"
    "- Prod `llm-monitoring-app_mlc-model` RW swap (q4 ara\u015ft\u0131rmas\u0131 "
    "\u00fcr\u00fcn\u00fc bekletmez; prod = base)\n"
    "- Image rebuild (`mlc-server-spike`)\n"
    "- Yeniden e\u011fitim (Problem B --- ayr\u0131 eksen)\n"
)
if start >= 0:
    text = text[:start] + phase + yasak
else:
    text = text.rstrip() + "\n\n" + phase + yasak

path.write_text(text, encoding="utf-8")
v = path.read_text(encoding="utf-8")
print("fused", "fused_dequantize" in v)
print("phase", "MLC_Q4_LMHEAD_HUNT" in v)
print("ctrl", (chr(12) in v) or (chr(8) in v))
print("Kanit", "Kan\u0131t" in v)
print("degil", "de\u011fil" in v)
for i, line in enumerate(v.splitlines(), 1):
    if 343 <= i <= 360:
        print(i, line)