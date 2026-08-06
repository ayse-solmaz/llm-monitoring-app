"""Single DeepKwiki-injected question with gateway ready-wait."""
import json
import sys
import time
import urllib.error
import urllib.request

GATEWAY = "http://localhost:8080"
CHAT = f"{GATEWAY}/v1/chat/completions"
MODEL = "/app/model"
TIMEOUT = 900


def wait_ready(max_wait: float = 120.0) -> bool:
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


def ask(content: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 48,
        "temperature": 0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        CHAT, data=data, headers={"Content-Type": "application/json"}
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = json.loads(resp.read())
    return {
        "answer": body["choices"][0]["message"]["content"].strip(),
        "seconds": round(time.time() - started, 1),
        "finish_reason": body["choices"][0].get("finish_reason"),
    }


def main() -> None:
    q = sys.argv[1] if len(sys.argv) > 1 else "Su kaç derecede kaynar?"
    wiki = sys.argv[2] if len(sys.argv) > 2 else (
        "Project facts: Deniz seviyesinde su 100 derecede kaynar."
    )
    content = f"{q}\n\n({wiki}; Answer with the correct well-known fact. Be brief.)"
    print("waiting for ready...", flush=True)
    if not wait_ready():
        print("gateway not ready", flush=True)
        sys.exit(1)
    print(f"asking: {q}", flush=True)
    try:
        result = ask(content)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:300]}", flush=True)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
