"""MLC gateway gecikme kiyasi.

Akisli bir istek atar; ilk token'a kadar gecen sure (TTFT) ile
decode hizini (token/sn) ayri ayri olcer. Ikisi ayri sorunlardir:
TTFT prefill maliyetini, decode hizi ise matmul verimini gosterir.

Kullanim:
    python scripts/bench_latency.py <etiket> [--tokens 32]

Sonuclar docs/bench/<etiket>.json altina yazilir.
"""

import argparse
import json
import pathlib
import time
import urllib.request

GATEWAY = "http://localhost:8080/v1/chat/completions"

PROMPTS = [
    "Turkiye'nin baskenti neresi?",
    "2 + 2 kactir?",
]


def stream_once(prompt: str, max_tokens: int) -> dict:
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": True,
    }
    req = urllib.request.Request(
        GATEWAY,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    start = time.perf_counter()
    ttft = None
    first_token_at = None
    tokens = 0
    pieces = []

    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            body = line[6:]
            if body == "[DONE]":
                break
            try:
                chunk = json.loads(body)
            except json.JSONDecodeError:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            piece = delta.get("content")
            if not piece:
                continue
            if ttft is None:
                ttft = time.perf_counter() - start
                first_token_at = time.perf_counter()
            tokens += 1
            pieces.append(piece)

    total = time.perf_counter() - start
    # Decode hizi ilk token'dan sonrasini olcer; prefill'i disarida birakir.
    decode_span = (time.perf_counter() - first_token_at) if first_token_at else 0.0
    decode_tps = (tokens - 1) / decode_span if tokens > 1 and decode_span > 0 else 0.0

    return {
        "prompt": prompt,
        "ttft_s": round(ttft, 2) if ttft else None,
        "total_s": round(total, 2),
        "tokens": tokens,
        "decode_tokens_per_s": round(decode_tps, 3),
        "s_per_token": round(total / tokens, 2) if tokens else None,
        "text": "".join(pieces),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--tokens", type=int, default=32)
    args = ap.parse_args()

    results = [stream_once(p, args.tokens) for p in PROMPTS]

    avg_tps = sum(r["decode_tokens_per_s"] for r in results) / len(results)
    out = {
        "label": args.label,
        "max_tokens": args.tokens,
        "avg_decode_tokens_per_s": round(avg_tps, 3),
        "runs": results,
    }

    dest = pathlib.Path("docs/bench")
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{args.label}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== {args.label} ===")
    for r in results:
        print(
            f"  TTFT {r['ttft_s']}s | toplam {r['total_s']}s | "
            f"{r['tokens']} token | decode {r['decode_tokens_per_s']} tok/s"
        )
        print(f"    -> {r['text'][:90]!r}")
    print(f"  ORTALAMA decode: {avg_tps:.3f} tok/s")
    print(f"  yazildi: {path}")


if __name__ == "__main__":
    main()
