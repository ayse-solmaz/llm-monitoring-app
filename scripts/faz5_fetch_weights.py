"""Yeni MLC agirliklarini indirir (Faz 5 B.3).

Yalnizca volume'a girecek dosyalar cekilir: params_shard_*.bin ve
tensor-cache.json. mlc-chat-config.json ve tokenizer dosyalari BILEREK
disarida birakilir — mevcut config derlenmis gemma-cpu.so ile eslesiyor.
"""

from pathlib import Path

from huggingface_hub import snapshot_download

REPO = "ayse-solmaz/gemma-2b-it-tr-mlc"
OUT = Path(__file__).resolve().parent.parent / "backups" / "new-weights"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(
        repo_id=REPO,
        local_dir=str(OUT),
        allow_patterns=["params_shard_*.bin", "tensor-cache.json"],
    )
    files = sorted(Path(path).glob("params_shard_*.bin"))
    total = sum(f.stat().st_size for f in files)
    print(f"dizin: {path}")
    print(f"shard: {len(files)} | toplam: {total / 1e9:.2f} GB")
    print("cache:", (Path(path) / "tensor-cache.json").exists())


if __name__ == "__main__":
    main()
