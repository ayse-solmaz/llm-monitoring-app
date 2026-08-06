"""short_answers.jsonl dosyasini train.jsonl icine tekrarsiz birlestirir.

Ayni instruction zaten varsa kisa cevapli surum tercih edilir: hedef davranis
"kisa soruya kisa cevap" oldugu icin uzun surum atilir.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "datasets"
TRAIN = ROOT / "train.jsonl"
SHORT = ROOT / "short_answers.jsonl"


def read(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> None:
    train = read(TRAIN)
    short = read(SHORT)

    by_instruction: dict[str, dict] = {}
    for row in train:
        key = row["instruction"].strip()
        existing = by_instruction.get(key)
        if existing is None or len(row["output"]) < len(existing["output"]):
            by_instruction[key] = row

    replaced = 0
    added = 0
    for row in short:
        key = row["instruction"].strip()
        if key in by_instruction:
            replaced += 1
        else:
            added += 1
        by_instruction[key] = row

    merged = list(by_instruction.values())
    with TRAIN.open("w", encoding="utf-8", newline="\n") as f:
        for row in merged:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"onceki: {len(train)} | tekrar temizlendi: {len(train) - len(by_instruction) + added + replaced}")
    print(f"kisa cevap: {added} eklendi, {replaced} mevcut satir kisa surumle degistirildi")
    print(f"yeni toplam: {len(merged)}")


if __name__ == "__main__":
    main()
