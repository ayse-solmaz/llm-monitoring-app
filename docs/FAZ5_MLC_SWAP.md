# Faz 5 — LoRA adaptörünü MLC'ye çevir ve volume'a al

> **Sonuç: Path A KAPANDI (2026-08-02).** İki swap denemesi başarısız.
> B.4 parametre kontrolü PASS; temiz koşullarda (CPU 6/6, penalty=0) ikinci
> deneme de bozuldu → ortam değil ağırlık kalitesi. Rollback tamam.
> Ayrıntı: [`FINETUNE_RESULTS.md`](FINETUNE_RESULTS.md) §5–§8.
>
> Ek olarak öğrenilen: gateway'de `messages + model + temperature` üzerinden
> anahtarlanan bir LRU önbellek var. Swap sonrası ölçümden önce
> `docker compose restart gateway` şart, yoksa eski cevaplar 0.0 saniyede
> geri gelir ve ölçüm sahte çıkar.

Tarih: 2026-08-01
Girdi: `ayse-solmaz/gemma-2b-it-tr-lora` (kök = epoch 3, `checkpoint-346/` = epoch 2)
Hedef: fine-tune edilmiş ağırlıkları `llm-monitoring-app_mlc-model` volume'una alıp `mlc` servisinde çalıştırmak.

---

## 0. Doğrulanan ve düzeltilen varsayımlar

| İddia | Durum |
|---|---|
| `convert_weight --lora-adapter` tek komutta merge eder | **Doğru.** `mlc-llm-cpu 0.20.0.dev0` wheel'i içinde bayrak mevcut; ayrı `peft merge` adımına gerek yok. |
| Faz 1.5'te Colab convert kanıtlandı | **Yanlış.** `docs/FAZ15_REPORT.md` §3: "kullanıcı testi bekleniyor". Convert bu fazda ilk kez çalışacak. |
| Volume'a `docker cp` ile yazılır | **Yanlış.** `mlc` servisinde mount **read-only** (`mlc-model:/app/model:ro`). Yazma, RW mount eden yardımcı container ile yapılmalı. |
| Eski model klasörü `rm -rf` ile temizlenir | **Tehlikeli.** `/app/model/gemma-cpu.so` derlenmiş TVM kütüphanesidir, image build'de üretilmiştir ve `convert_weight` çıktısında **yoktur**. Silinirse servis açılmaz ve yeniden derlemek 45-90 dk sürer. |
| Yedek `/app/model.backup` içine alınır | **Zayıf.** Orası container'ın yazılabilir katmanı; `restart` hayatta bırakır ama `up --force-recreate` siler. Yedek host'a alınmalı. |

### Neden yalnızca ağırlıklar değişecek

`gemma-cpu.so`, mevcut `mlc-chat-config.json` ile derlendi (`context_window_size: 8192`, `q4f16_1`, `gemma`). LoRA merge mimariyi ve tensör şekillerini değiştirmez; yalnızca ağırlık **değerleri** değişir. Dolayısıyla:

- **Değişecek:** `params_shard_*.bin`, `ndarray-cache.json`, **`tensor-cache.json`**
- **Korunacak:** `gemma-cpu.so`, `mlc-chat-config.json`, tokenizer dosyaları

Config'i de değiştirirsek `.so` ile uyuşmazlık riski doğar (derleme zamanı sabitleri farklılaşır). Yeni config üretilip **karşılaştırılacak**, ama varsayılan olarak eski config korunacak.

### Mevcut volume envanteri (2026-08-01, B.0)

| Öğe | Değer |
|---|---|
| Volume | `llm-monitoring-app_mlc-model` |
| Toplam boyut | 2.7 GB (bunun 1.3 GB'ı gereksiz `.git` — HF clone kalıntısı) |
| Ağırlıklar | **38 shard**, 1.3 GB (`params_shard_0.bin` … `params_shard_37.bin`) |
| Cache | `ndarray-cache.json` = `tensor-cache.json` (aynı md5: `3ed0be04…`) — **ikisini birden değiştir** |
| `.so` | `gemma-cpu.so` 1.788.200 bayt — dokunma |
| Config | `model_type: gemma`, `q4f16_1`, `context_window_size: 8192`, `stop_token_ids: [1, 107]` |
| Host yedek | `backups/mlc-model-backup-20260801-082237.tar.gz` (2.3 GB) |
| Baseline | `backups/faz5-before.json` — 6/6 yanlış (başkent = Abuja) |

---

## Bölüm A — Convert (Kaggle/Colab, kullanıcı çalıştırır)

CPU yeterli, GPU gerekmez. Kaggle tercih edilir (30 GB RAM, merge sırasında rahat).

### A.1 Kurulum ve bayrak doğrulaması

```python
!pip install -q --upgrade pip
!pip install -q --pre -f https://mlc.ai/wheels --only-binary=:all: \
  "mlc-ai-cpu==0.20.0" "mlc-llm-cpu==0.20.0.dev0"
!pip install -q "apache-tvm-ffi==0.1.10" transformers sentencepiece safetensors

!python -m mlc_llm convert_weight --help
```

Çıktıda `--lora-adapter` görünmeli. Görünmüyorsa dur ve bildir; o durumda önce `peft` ile merge edip birleştirilmiş modeli kaydetmek gerekir.

### A.2 Base ve adaptörü indir

```python
from huggingface_hub import login, snapshot_download

login()  # read yetkisi yeter

snapshot_download("google/gemma-2b-it", local_dir="./gemma-base")
snapshot_download("ayse-solmaz/gemma-2b-it-tr-lora", local_dir="./tr-lora")

!ls ./tr-lora
```

`adapter_config.json` ve `adapter_model.safetensors` kökte olmalı. `checkpoint-346/` alt klasörü yok sayılır; epoch 2'yi denemek isterseniz `--lora-adapter ./tr-lora/checkpoint-346` verin.

### A.3 Convert (merge + quantize)

```python
!python -m mlc_llm convert_weight ./gemma-base \
  --quantization q4f16_1 \
  --model-type gemma \
  --lora-adapter ./tr-lora \
  -o ./gemma-tr-mlc
```

`--model-type gemma` zorunlu; `gemma2` Gemma 2 mimarisidir, uymaz.

### A.4 Config üret — ayrı klasöre

```python
!python -m mlc_llm gen_config ./gemma-base \
  --quantization q4f16_1 \
  --conv-template gemma_instruction \
  -o ./gemma-tr-config
```

Ayrı klasör bilinçli: üretilen config'i mevcut çalışan config ile karşılaştıracağız, körlemesine üzerine yazmayacağız.

### A.5 Çıktı kontrolü

```python
!ls -lh ./gemma-tr-mlc/
import json
print(json.load(open("./gemma-tr-config/mlc-chat-config.json"))["context_window_size"])
```

Beklenen: `params_shard_*.bin` dosyaları, `ndarray-cache.json`, toplam ~1.5 GB. Context window 8192 çıkmalı; farklıysa bildir.

### A.6 Çıktıyı taşı — HF üzerinden (önerilen)

1.5 GB'ı tarayıcıdan indirmek yavaş ve kopma riski yüksek. Hub üzerinden gitmek daha güvenilir:

```python
from huggingface_hub import HfApi, whoami

repo = f"{whoami()['name']}/gemma-2b-it-tr-q4f16_1-MLC"
api = HfApi()
api.create_repo(repo, private=True, exist_ok=True)
api.upload_folder(folder_path="./gemma-tr-mlc", repo_id=repo)
print(repo)
```

Yedek yol: `!zip -r gemma-tr-mlc.zip ./gemma-tr-mlc/` ve sol panelden indir.

---

## Bölüm B — Volume swap (agent çalıştırır, Docker Desktop açık olmalı)

### B.1 Ön kontrol ve mevcut içerik envanteri

```powershell
docker compose ps
curl.exe -s http://localhost:8080/healthz
docker run --rm -v llm-monitoring-app_mlc-model:/data alpine ls -la /data
```

`.so` dosyasının adı ve config'in varlığı buradan teyit edilir.

### B.2 Baseline ölçüm (swap öncesi)

Altı soru, `max_tokens: 64`, `temperature: 0`, model id `/app/model`. Cevaplar "ÖNCE" sütunu olur.

### B.3 Yedek — host'a (atlanmaz)

```powershell
docker run --rm -v llm-monitoring-app_mlc-model:/data -v "${PWD}\backups:/backup" `
  alpine tar czf /backup/mlc-model-backup.tar.gz -C /data .
```

`backups\mlc-model-backup.tar.gz` oluştuğu ve boyutunun ~1.5 GB olduğu doğrulanır. Container içine yedek alınmaz.

### B.4 Yalnızca ağırlıkları değiştir

Yeni çıktıda `tensor-cache.json` yoksa (yalnızca `ndarray-cache.json` varsa) ikisine de aynı dosyayı kopyala — mevcut volume'da bunlar birebir kopya.

```powershell
docker run --rm `
  -v llm-monitoring-app_mlc-model:/data `
  -v "<yeni-agirliklarin-host-yolu>:/new:ro" `
  alpine sh -c "
    rm -f /data/params_shard_*.bin /data/ndarray-cache.json /data/tensor-cache.json
    cp /new/params_shard_*.bin /new/ndarray-cache.json /data/
    if [ -f /new/tensor-cache.json ]; then
      cp /new/tensor-cache.json /data/
    else
      cp /data/ndarray-cache.json /data/tensor-cache.json
    fi
    ls -la /data
    ls /data/gemma-cpu.so /data/mlc-chat-config.json /data/tokenizer.json
  "
```

`gemma-cpu.so`, `mlc-chat-config.json` ve tokenizer dosyalarına dokunulmaz.

### B.5 Restart ve hazır bekle

```powershell
docker compose restart mlc
curl.exe -s http://localhost:8080/healthz    # ready: true (60-180 sn sürebilir)
curl.exe -s http://localhost:8080/v1/models
```

### B.6 Aynı altı soru — "SONRA" sütunu

### B.7 Değerlendirme

- **Biçim:** kısa mı, tekrarsız mı, düzgün duruyor mu → iyileşme **bekleniyor**
- **Olgu:** doğruluk → belirgin iyileşme **beklenmiyor**, DeepKwiki işi

### B.8 Rollback

Tetikleyiciler: `healthz` ready olmuyor, servis çöküyor, cevaplar base'den belirgin kötü (bozuk karakter, alakasız çıktı).

```powershell
docker run --rm -v llm-monitoring-app_mlc-model:/data -v "${PWD}\backups:/backup" `
  alpine sh -c "rm -rf /data/* && tar xzf /backup/mlc-model-backup.tar.gz -C /data"
docker compose restart mlc
curl.exe -s http://localhost:8080/healthz
```

Epoch 3 kötü çıkarsa Bölüm A'yı `--lora-adapter ./tr-lora/checkpoint-346` ile tekrarla.

---

## Yasaklar

- `mlc-server-spike` image'ını yeniden derleme
- Yedek almadan swap
- `MAX_INFLIGHT` değiştirme
- `gemma-cpu.so` silme
- Olgusal hatalar için yeniden eğitim (RAG/DeepKwiki işi)
