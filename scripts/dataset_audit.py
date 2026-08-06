"""Egitim setinin davranis dagilimini olcer.

Amac: modelin ogrenecegi cevap uslubunu tahmin etmek. Kisa olgusal cevap ornegi
yoksa model her soruya uzun aciklama yazmayi ogrenir.
"""

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "datasets" / "train.jsonl"
QA_PATTERN = re.compile(r"\?|nedir|neden|nasıl|hangi|kimdir|kaç|ne zaman|nerede", re.IGNORECASE)


def main() -> None:
    out = sys.stdout
    rows = []
    for line in DATA.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    qa = [r for r in rows if QA_PATTERN.search(r.get("instruction", ""))]
    chatty = [r for r in rows if not QA_PATTERN.search(r.get("instruction", ""))]

    print(f"toplam: {len(rows)} | qa: {len(qa)} | sohbet: {len(chatty)}", file=out)

    lengths = [len(r.get("output", "")) for r in qa]
    print(
        f"qa cevap uzunlugu -> medyan {statistics.median(lengths)} "
        f"| ort {round(sum(lengths) / len(lengths))} | max {max(lengths)}",
        file=out,
    )

    buckets = Counter()
    for n in lengths:
        if n < 40:
            buckets["<40 (tek kelime/kisa)"] += 1
        elif n < 80:
            buckets["40-80 (tek cumle)"] += 1
        elif n < 160:
            buckets["80-160 (aciklamali)"] += 1
        else:
            buckets["160+ (uzun)"] += 1
    for key in ["<40 (tek kelime/kisa)", "40-80 (tek cumle)", "80-160 (aciklamali)", "160+ (uzun)"]:
        n = buckets[key]
        print(f"  {key:<24} {n:>5}  ({100 * n / len(lengths):.1f}%)", file=out)

    print("\nbasit olgusal soru kapsamasi:", file=out)
    for kw in ["başkent", "kaynar", "2+2", "Ankara", "kaç eder", "hangi yıl"]:
        hits = sum(1 for r in rows if kw.lower() in (r.get("instruction", "") + " " + r.get("output", "")).lower())
        print(f"  {kw:<12} {hits}", file=out)

    short = [r for r in qa if len(r.get("output", "")) < 40]
    print(f"\n40 karakterden kisa cevap ornegi ({len(short)} adet):", file=out)
    for r in short[:10]:
        print(f"  S: {r['instruction'][:70]}", file=out)
        print(f"  C: {r['output'][:70]}", file=out)


if __name__ == "__main__":
    main()
