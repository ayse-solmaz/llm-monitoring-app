# q4f32_1 reformat — agent runbook (Part 2+)

Durum: **Part 1 hazır.** Kullanıcı Kaggle/Colab hücrelerini çalıştırıp HF’ye yükleyene kadar Part 2 beklemede.

## Part 1 (tamam)

| Dosya | Rol |
|---|---|
| [`notebooks/mlc_q4f32_convert_cells.md`](../notebooks/mlc_q4f32_convert_cells.md) | Kopyala-yapıştır hücreler |
| [`notebooks/mlc_q4f32_convert.py`](../notebooks/mlc_q4f32_convert.py) | Birleşik referans |

Fark (önceki Path A): fp32 merge → tek niceleme `q4f32_1` → **yeni** `gemma-cpu.so`. Volume’da shards + cache + `.so` + `mlc-chat-config.json` değişir.

## Part 2 tetikleyici

Kullanıcı şunu getirince başla:

1. Cell 8: `ls -lh` + quantization / ELF / shard özeti
2. Cell 9: `ayse-solmaz/gemma-2b-it-tr-q4f32` (veya `whoami` adı) upload OK

Adımlar (özet):

1. Baseline: `backups/faz5-clean-before.json` varsa kullan; yoksa `faz5_ask.py`
2. Host tar yedek: `mlc-model-pre-q4f32-<ts>.tar.gz`
3. `snapshot_download` → `backups/q4f32-weights`
4. Uyumluluk: `q4f32_1` config, ELF `.so`, shards ~1.4 GB
5. `docker compose stop mlc` → RW alpine helper → replace shards/cache/so/config (tokenizer opsiyonel overwrite)
6. `docker compose start mlc` + gateway restart (LRU)
7. `python scripts/faz5_ask.py q4f32-after`
8. Karşılaştır; gibberish / healthz fail → rollback

## Kısıtlar

- `mlc-server-spike` image rebuild YOK
- `MAX_INFLIGHT` değiştirme
- Yeniden eğitim önerme
- Her swap öncesi yedek
