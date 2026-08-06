"""
Phase 2 — DeepKwiki inject eval (mirrors frontend webmcp assembly).
No model retrain. Uses local gateway :8080.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

GATEWAY = "http://localhost:8080"
CHAT = f"{GATEWAY}/v1/chat/completions"
MODEL = "/app/model"
TIMEOUT = 900
OUT = Path(__file__).resolve().parents[1] / "backups" / "phase2-deepkwiki-eval.json"

# Same bodies as frontend/src/lib/deepkwiki.ts PROJECT_FACTS (keep in sync).
FACTS = {
    "physics-water-boil": (
        "Su kaynama sıcaklığı: Deniz seviyesinde su 100 derecede (100°C) kaynar."
    ),
    "backend-stack": (
        "Backend dili ve stack: Bu projenin backend'i Go (Golang) ile yazılmıştır: "
        "Gin, GORM, PostgreSQL."
    ),
    "jwt-tokens": (
        "JWT access ve refresh süreleri: Access token 15 dakika geçerlidir. "
        "Refresh token 7 gün geçerlidir."
    ),
}

PATTERNS = [
    (re.compile(r"su\s+kaç|kaç\s+derece.*kaynar|kaynama|water.*boil", re.I), "physics-water-boil"),
    (
        re.compile(
            r"backend.*(dil|language)|projenin\s+backend|hangi\s+(dil|language).*backend|backend\s+dili",
            re.I,
        ),
        "backend-stack",
    ),
    (
        re.compile(
            r"access\s*token|token\s+kaç\s+dakika|jwt.*(dakika|süre)|refresh\s*token.*geçer",
            re.I,
        ),
        "jwt-tokens",
    ),
]

QUESTIONS = [
    {
        "id": "baskent",
        "q": "Türkiye'nin başkenti nedir?",
        "kind": "factual",
        "expect": re.compile(r"ankara", re.I),
        "inject": False,
    },
    {
        "id": "two_plus_two",
        "q": "2+2 kaç eder?",
        "kind": "factual",
        "expect": re.compile(r"\b4\b|dört", re.I),
        "inject": False,
    },
    {
        "id": "water",
        "q": "Su kaç derecede kaynar?",
        "kind": "factual",
        "expect": re.compile(r"100", re.I),
        "inject": True,
    },
    {
        "id": "backend",
        "q": "Bu projenin backend dili nedir?",
        "kind": "factual",
        "expect": re.compile(r"\bgo\b|golang", re.I),
        "inject": True,
    },
    {
        "id": "token",
        "q": "Access token kaç dakika geçerlidir?",
        "kind": "factual",
        "expect": re.compile(r"15", re.I),
        "inject": True,
    },
    {
        "id": "merhaba",
        "q": "Merhaba",
        "kind": "ood",
        "expect": None,
        "inject": False,
    },
]


def wait_ready(max_wait: float = 180.0) -> bool:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{GATEWAY}/healthz", timeout=10) as resp:
                body = json.loads(resp.read())
            if body.get("ready"):
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def pick_fact(q: str) -> str | None:
    for pat, fid in PATTERNS:
        if pat.search(q):
            return FACTS[fid]
    return None


def build_content(q: str, inject: bool) -> tuple[str, str | None]:
    parts: list[str] = []
    wiki_id = None
    if inject:
        fact = pick_fact(q)
        if fact:
            parts.append(f"Project facts — answer from these if they apply:\n{fact}")
            wiki_id = fact.split(":", 1)[0]
    looks_tr = bool(
        re.search(r"[ğüşıöçĞÜŞİÖÇ]", q)
        or re.search(r"\b(nedir|neresi|kaç|nasıl)\b", q, re.I)
    )
    if looks_tr:
        parts.append("Answer with the correct well-known fact. Be brief.")
    if parts:
        return f"{q}\n\n({'; '.join(parts)})", wiki_id
    return q, wiki_id


def ask(content: str, retries: int = 5) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 48,
        "temperature": 0,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(retries):
        if not wait_ready(180):
            raise RuntimeError("gateway not ready")
        req = urllib.request.Request(
            CHAT, data=data, headers={"Content-Type": "application/json"}
        )
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = json.loads(resp.read())
            choice = body["choices"][0]
            return {
                "answer": (choice.get("message") or {}).get("content", "").strip(),
                "finish_reason": choice.get("finish_reason"),
                "seconds": round(time.time() - started, 1),
            }
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 503) and attempt + 1 < retries:
                print(f"  retry after HTTP {exc.code} (attempt {attempt + 1})...", flush=True)
                time.sleep(10)
                continue
            raise
    raise last_err or RuntimeError("ask failed")


def main() -> None:
    print("waiting for gateway ready...", flush=True)
    if not wait_ready():
        print("FAIL: gateway not ready", flush=True)
        raise SystemExit(1)

    rows = []
    factual_ok = 0
    factual_n = 0

    for item in QUESTIONS:
        content, wiki = build_content(item["q"], item["inject"])
        print(f"\n=== {item['id']}: {item['q']}", flush=True)
        if wiki:
            print(f"  inject: {wiki}", flush=True)
        try:
            result = ask(content)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:200]
            print(f"  HTTP {exc.code}: {detail}", flush=True)
            rows.append(
                {
                    "id": item["id"],
                    "q": item["q"],
                    "kind": item["kind"],
                    "injected": bool(wiki),
                    "wiki": wiki,
                    "error": f"HTTP {exc.code}",
                    "pass": False,
                }
            )
            if item["kind"] == "factual":
                factual_n += 1
            continue
        except Exception as exc:
            print(f"  ERROR: {exc}", flush=True)
            rows.append(
                {
                    "id": item["id"],
                    "q": item["q"],
                    "kind": item["kind"],
                    "injected": bool(wiki),
                    "wiki": wiki,
                    "error": str(exc),
                    "pass": False,
                }
            )
            if item["kind"] == "factual":
                factual_n += 1
            continue

        answer = result["answer"]
        fr = result["finish_reason"]
        print(f"  answer: {answer[:200]!r}", flush=True)
        print(f"  finish: {fr}  ({result['seconds']}s)", flush=True)

        if item["kind"] == "ood":
            ok = fr in ("stop", "length")
            note = "ood_ok"
        else:
            factual_n += 1
            ok = bool(item["expect"].search(answer)) and fr == "stop"
            if ok:
                factual_ok += 1
            note = "match" if ok else "miss"

        rows.append(
            {
                "id": item["id"],
                "q": item["q"],
                "kind": item["kind"],
                "injected": bool(wiki),
                "wiki": wiki,
                "answer": answer,
                "finish_reason": fr,
                "seconds": result["seconds"],
                "pass": ok,
                "note": note,
            }
        )
        time.sleep(2)

    summary = {
        "factual_pass": factual_ok,
        "factual_total": factual_n,
        "success_bar": "5/5 factual stop+correct; Merhaba OOD not blocker",
        "pass": factual_ok == factual_n and factual_n == 5,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SUMMARY", flush=True)
    print(
        json.dumps({"factual": f"{factual_ok}/{factual_n}", "pass": summary["pass"]}, indent=2),
        flush=True,
    )
    print(f"wrote {OUT}", flush=True)
    raise SystemExit(0 if summary["pass"] else 1)


if __name__ == "__main__":
    main()
