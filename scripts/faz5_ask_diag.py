"""Ask six questions against diag MLC on :8088 (prod :8080 untouched).

Usage:
    python scripts/faz5_ask_diag.py q0f16-diag
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GATEWAY = "http://localhost:8088/v1/chat/completions"
MODEL = "/app/model"
TIMEOUT = 900

# Order: 5 factual + 1 conversational (Merhaba not a blocker)
QUESTIONS = [
    "Türkiye'nin başkenti neresidir?",
    "2+2 kaç eder?",
    "Su kaç derecede kaynar?",
    "Bu projenin backend dili nedir?",
    "Access token kaç dakika geçerlidir?",
    "Merhaba, nasılsın?",
]

FACTUAL = set(QUESTIONS[:5])


def ask(question: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": 64,
        "temperature": 0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GATEWAY, data=data, headers={"Content-Type": "application/json"}
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - started
        choice = body["choices"][0]
        answer = (choice.get("message") or {}).get("content") or ""
        usage = body.get("usage") or {}
        return {
            "question": question,
            "kind": "factual" if question in FACTUAL else "conversational",
            "answer": answer.strip(),
            "seconds": round(elapsed, 1),
            "completion_tokens": usage.get("completion_tokens"),
            "finish_reason": choice.get("finish_reason"),
        }
    except urllib.error.HTTPError as exc:
        return {
            "question": question,
            "kind": "factual" if question in FACTUAL else "conversational",
            "error": f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:300]}",
            "seconds": round(time.time() - started, 1),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "question": question,
            "kind": "factual" if question in FACTUAL else "conversational",
            "error": f"{type(exc).__name__}: {exc}",
            "seconds": round(time.time() - started, 1),
        }


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "q0f16-diag"
    out_dir = Path(__file__).resolve().parent.parent / "backups"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"faz5-{label}.json"

    rows = [ask(q) for q in QUESTIONS]
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    for r in rows:
        fr = r.get("finish_reason")
        ans = (r.get("answer") or r.get("error") or "")[:80]
        print(f"[{r['kind']}] finish={fr} | {r['question'][:40]} -> {ans}")


if __name__ == "__main__":
    main()
