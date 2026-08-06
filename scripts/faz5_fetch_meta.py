"""Yeni MLC artifact'inin yalnizca metadata dosyalarini indirir.

Agirliklari (1.4 GB) indirmeden once parametre uyumlulugunu dogrulamak icin.
"""

from pathlib import Path

from huggingface_hub import hf_hub_download

REPO = "ayse-solmaz/gemma-2b-it-tr-mlc"
OUT = Path(__file__).resolve().parent.parent / "backups" / "new-meta"
FILES = ["tensor-cache.json", "mlc-chat-config.json"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        try:
            path = hf_hub_download(repo_id=REPO, filename=name, local_dir=str(OUT))
            print(f"indirildi: {name} -> {path}")
        except Exception as exc:  # noqa: BLE001
            print(f"ALINAMADI: {name} ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    main()
