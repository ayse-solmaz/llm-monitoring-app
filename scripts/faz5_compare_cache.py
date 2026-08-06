"""Eski ve yeni MLC parametre kayitlarini karsilastirir (Faz 5 B.4).

Shard sayisinin farkli olmasi tek basina uyumsuzluk demek degildir; derlenmis
gemma-cpu.so parametre kumesini umursar, dosyalara nasil bolundugunu degil.
Bu yuzden ad / sekil / dtype duzeyinde karsilastirma yapilir.

Cikis kodu 0 = swap guvenli, 1 = DUR.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "backups"
OLD = ROOT / "old-meta" / "ndarray-cache.json"
NEW = ROOT / "new-meta" / "tensor-cache.json"


def load_records(path: Path) -> tuple[dict, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records: dict[str, dict] = {}
    shards = set()

    for shard in data.get("records", []):
        shard_name = shard.get("dataPath")
        if shard_name:
            shards.add(shard_name)
        for entry in shard.get("records", []):
            records[entry["name"]] = {
                "shape": tuple(entry.get("shape", [])),
                "dtype": entry.get("dtype"),
                "format": entry.get("format"),
            }

    meta = {
        "top_level_keys": sorted(data.keys()),
        "metadata": data.get("metadata"),
        "shard_count": len(shards),
        "param_count": len(records),
    }
    return records, meta


def main() -> None:
    if not OLD.exists() or not NEW.exists():
        print(f"dosya eksik: {OLD.exists()=} {NEW.exists()=}")
        sys.exit(1)

    old, old_meta = load_records(OLD)
    new, new_meta = load_records(NEW)

    print("=== SEMA ===")
    print("eski ust seviye anahtarlar:", old_meta["top_level_keys"])
    print("yeni ust seviye anahtarlar:", new_meta["top_level_keys"])
    print("eski metadata:", old_meta["metadata"])
    print("yeni metadata:", new_meta["metadata"])
    print(f"\neski shard: {old_meta['shard_count']} | yeni shard: {new_meta['shard_count']}")
    print(f"eski parametre: {old_meta['param_count']} | yeni parametre: {new_meta['param_count']}")

    old_names = set(old)
    new_names = set(new)

    only_old = sorted(old_names - new_names)
    only_new = sorted(new_names - old_names)

    print("\n=== AD KARSILASTIRMASI ===")
    print(f"yalnizca eskide: {len(only_old)}")
    for n in only_old[:15]:
        print("   -", n)
    print(f"yalnizca yenide: {len(only_new)}")
    for n in only_new[:15]:
        print("   +", n)

    shape_diff = []
    dtype_diff = []
    for name in sorted(old_names & new_names):
        if old[name]["shape"] != new[name]["shape"]:
            shape_diff.append((name, old[name]["shape"], new[name]["shape"]))
        if old[name]["dtype"] != new[name]["dtype"]:
            dtype_diff.append((name, old[name]["dtype"], new[name]["dtype"]))

    print("\n=== SEKIL / DTYPE ===")
    print(f"sekil farki: {len(shape_diff)}")
    for name, a, b in shape_diff[:15]:
        print(f"   {name}: {a} -> {b}")
    print(f"dtype farki: {len(dtype_diff)}")
    for name, a, b in dtype_diff[:15]:
        print(f"   {name}: {a} -> {b}")

    print("\n=== ORNEK PARAMETRE ADLARI (yeni) ===")
    for name in sorted(new_names)[:8]:
        print(f"   {name}  {new[name]['shape']}  {new[name]['dtype']}")

    ok = not only_old and not only_new and not shape_diff and not dtype_diff
    print("\n=== SONUC ===")
    if ok:
        print("GECTI: parametre kumesi birebir ayni. Yalnizca shard bolunmesi farkli.")
        print("Swap guvenli.")
        sys.exit(0)
    print("DUR: parametre kumesi farkli. .so yeni agirliklarla uyusmaz.")
    sys.exit(1)


if __name__ == "__main__":
    main()
