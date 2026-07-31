"""Deduplicate datasets/train.jsonl and append project-specific examples.

Usage:
    python scripts/dataset_dedupe.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAIN = ROOT / "datasets" / "train.jsonl"
EXTRA = ROOT / "datasets" / "project_examples.jsonl"


def load(path):
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path.name}:{lineno} invalid JSON: {exc}")
    return rows


def key(row):
    return (row.get("instruction", "").strip(), row.get("output", "").strip())


def main():
    original = load(TRAIN)
    extra = load(EXTRA) if EXTRA.exists() else []

    seen = set()
    kept = []
    for row in original + extra:
        k = key(row)
        if k in seen:
            continue
        seen.add(k)
        kept.append(row)

    with TRAIN.open("w", encoding="utf-8", newline="\n") as fh:
        for row in kept:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"original: {len(original)}")
    print(f"project examples: {len(extra)}")
    print(f"duplicates removed: {len(original) + len(extra) - len(kept)}")
    print(f"final: {len(kept)}")


if __name__ == "__main__":
    main()
