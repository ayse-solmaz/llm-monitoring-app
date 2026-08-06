"""Faz 5 karsilastirma olcumu: sabit alti soruyu gateway'e sorar.

Kullanim:
    python scripts/faz5_ask.py before
    python scripts/faz5_ask.py after

Sonuc backups/faz5-<etiket>.json dosyasina yazilir. Swap oncesi ve sonrasi
ayni parametrelerle calistirilmalidir, yoksa karsilastirma anlamsiz olur.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GATEWAY = "http://localhost:8080/v1/chat/completions"
MODEL = "/app/model"
TIMEOUT = 900

QUESTIONS = [
    "Türkiye'nin başkenti neresidir?",
    "2+2 kaç eder?",
    "Su kaç derecede kaynar?",
    "Bu projenin backend dili nedir?",
    "Access token kaç dakika geçerlidir?",
    "Merhaba, nasılsın?",
]


def ask(question: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": 64,
        "temperature": 0,
        # Clean Path-A retry: override model-config default frequency_penalty=1.0
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
        answer = body["choices"][0]["message"]["content"].strip()
        usage = body.get("usage") or {}
        return {
            "question": question,
            "answer": answer,
            "seconds": round(elapsed, 1),
            "completion_tokens": usage.get("completion_tokens"),
            "finish_reason": body["choices"][0].get("finish_reason"),
        }
    except urllib.error.HTTPError as exc:
        return {
            "question": question,
            "error": f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:300]}",
            "seconds": round(time.time() - started, 1),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "question": question,
            "error": f"{type(exc).__name__}: {exc}",
            "seconds": round(time.time() - started, 1),
        }


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "before"
    out_dir = Path(__file__).resolve().parent.parent / "backups"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"faz5-{label}.json"

    results = []
    for i, question in enumerate(QUESTIONS, 1):
        print(f"[{i}/{len(QUESTIONS)}] {question}", flush=True)
        result = ask(question)
        results.append(result)
        if "error" in result:
            print(f"    HATA ({result['seconds']}s): {result['error']}", flush=True)
        else:
            print(
                f"    ({result['seconds']}s, {result['completion_tokens']} token, "
                f"{result['finish_reason']}) {result['answer']}",
                flush=True,
            )

    out_path.write_text(
        json.dumps({"label": label, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nkaydedildi: {out_path}")


if __name__ == "__main__":
    main()
