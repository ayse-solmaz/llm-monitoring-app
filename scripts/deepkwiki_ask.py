"""Problem B — DeepKwiki context injection smoke test.

Runs three factual questions against the MLC gateway:
  1) raw prompt (no context) — expect wrong facts
  2) DeepKwiki-injected prompt — expect correct facts

Usage:
    python scripts/deepkwiki_ask.py

Requires gateway at http://localhost:8080 (docker compose up).
"""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

GATEWAY = "http://localhost:8080/v1/chat/completions"
HEALTHZ = "http://localhost:8080/healthz"
MODEL = "/app/model"
TIMEOUT = 900

QUESTIONS = [
    {
        "question": "Su kaç derecede kaynar?",
        "pattern": re.compile(r"100", re.I),
        "wiki_id": "physics-water-boil",
        "wiki_body": "Deniz seviyesinde su 100 derecede (100°C) kaynar.",
    },
    {
        "question": "Bu projenin backend dili nedir?",
        "pattern": re.compile(r"\bgo\b|golang", re.I),
        "wiki_id": "backend-stack",
        "wiki_body": "Bu projenin backend'i Go (Golang) ile yazılmıştır: Gin, GORM, PostgreSQL.",
    },
    {
        "question": "Access token kaç dakika geçerlidir?",
        "pattern": re.compile(r"\b15\b"),
        "wiki_id": "jwt-tokens",
        "wiki_body": "Access token 15 dakika geçerlidir. Refresh token 7 gün geçerlidir.",
    },
]


def format_wiki_context(title: str, body: str) -> str:
    return f"Project facts (use only if relevant):\n{title}: {body}"


def build_injected_prompt(question: str, wiki_title: str, wiki_body: str) -> str:
    wiki_block = format_wiki_context(wiki_title, wiki_body)
    accuracy = "Answer with the correct well-known fact. Be brief."
    return f"{question}\n\n({wiki_block}; {accuracy})"


def wait_ready(max_wait: float = 180.0) -> bool:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTHZ, timeout=10) as resp:
                body = json.loads(resp.read())
            if body.get("ready"):
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def ask(content: str, max_tokens: int = 48) -> dict:
    if not wait_ready():
        return {"error": "gateway not ready", "seconds": 0.0}
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
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
        return {
            "answer": choice["message"]["content"].strip(),
            "seconds": round(elapsed, 1),
            "completion_tokens": (body.get("usage") or {}).get("completion_tokens"),
            "finish_reason": choice.get("finish_reason"),
        }
    except urllib.error.HTTPError as exc:
        return {
            "error": f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:300]}",
            "seconds": round(time.time() - started, 1),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "seconds": round(time.time() - started, 1),
        }


def main() -> None:
    results = []
    for item in QUESTIONS:
        q = item["question"]
        print(f"\n=== {q} ===", flush=True)

        raw = ask(q)
        time.sleep(10)
        injected = ask(
            build_injected_prompt(q, item["wiki_id"], item["wiki_body"])
        )
        time.sleep(10)

        raw_ok = (
            bool(raw.get("answer"))
            and bool(item["pattern"].search(raw["answer"]))
        )
        inj_ok = (
            bool(injected.get("answer"))
            and bool(item["pattern"].search(injected["answer"]))
        )

        if "error" in raw:
            print(f"  RAW ERROR: {raw['error']}", flush=True)
        else:
            print(f"  RAW ({raw['seconds']}s): {raw['answer']}", flush=True)
            print(f"  RAW pass: {raw_ok}", flush=True)

        if "error" in injected:
            print(f"  INJECT ERROR: {injected['error']}", flush=True)
        else:
            print(f"  INJECT ({injected['seconds']}s): {injected['answer']}", flush=True)
            print(f"  INJECT pass: {inj_ok}", flush=True)

        results.append(
            {
                "question": q,
                "raw": raw,
                "injected": injected,
                "raw_pass": raw_ok,
                "injected_pass": inj_ok,
            }
        )

    out = Path(__file__).resolve().parent.parent / "backups" / "deepkwiki-smoke.json"
    out.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {out}", flush=True)

    inj_pass = sum(1 for r in results if r["injected_pass"])
    print(f"\nDeepKwiki injected: {inj_pass}/{len(results)} passed", flush=True)


if __name__ == "__main__":
    main()
