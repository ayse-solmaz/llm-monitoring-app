"""Ceza parametrelerinin bozulmaya sebep olup olmadigini test eder.

mlc-chat-config.json varsayilanlari: frequency_penalty 1.0, top_p 0.95.
Yuksek frequency_penalty, dogru kisa cevaptan sonraki dogal devam token'larini
cezalandirip modeli tuhaf kelimelere itebilir. Bu betik ayni sorulari cezalar
kapali halde sorar; cevaplar duzeliyorsa sorun agirliklarda degil orneklemede.
"""

import json
import sys
import time
import urllib.request

GATEWAY = "http://localhost:8080/v1/chat/completions"

QUESTIONS = [
    "Türkiye'nin başkenti neresidir?",
    "2+2 kaç eder?",
    "Merhaba, nasılsın?",
]


def ask(question: str, **overrides) -> None:
    payload = {
        "model": "/app/model",
        "messages": [{"role": "user", "content": question}],
        "max_tokens": 64,
        "temperature": 0,
        "stream": False,
    }
    payload.update(overrides)

    req = urllib.request.Request(
        GATEWAY,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=900) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    choice = body["choices"][0]
    print(f"S: {question}")
    print(f"C: {choice['message']['content'].strip()}")
    print(f"   ({time.time() - started:.0f}s, finish={choice.get('finish_reason')})\n", flush=True)


def main() -> None:
    print("=== CEZALAR KAPALI (frequency_penalty=0, presence_penalty=0, top_p=1) ===\n")
    for q in QUESTIONS:
        ask(q, frequency_penalty=0, presence_penalty=0, top_p=1.0)


if __name__ == "__main__":
    main()
