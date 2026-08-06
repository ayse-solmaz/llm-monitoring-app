# Fine-tune dataset (Gemma 2B-IT / QLoRA)

Bu klasör Colab QLoRA eğitimi için JSONL veri içerir. Base model: **`google/gemma-2b-it`** (Gemma 1 — `gemma-2-2b-it` değil).

## Dosyalar

| Dosya | Amaç |
|-------|------|
| `seed_examples.jsonl` | 20 örnek şablon (5 kategori × 4). Referans / kalite ölçütü. |
| `train.jsonl` | Asıl eğitim seti (~4.100 satır). Colab notebook bunu okur. |
| `short_answers.jsonl` | 135 kısa cevap örneği. `scripts/dataset_merge_short.py` ile `train.jsonl`'e katılır. |

## Cevap uzunluğu dengesi

`scripts/dataset_audit.py` eğitim setindeki cevap uzunluklarını raporlar. İlk eğitim turunda QA cevaplarının %95'i 80 karakterden uzundu; model bu yüzden "2+2 kaç eder?" gibi basit sorulara bile paragraf yazmayı öğrendi. `short_answers.jsonl` bu dengeyi düzeltmek için eklendi.

Yeni satır eklerken hedef: **soru kısaysa cevap da kısa olsun.** "Türkiye'nin başkenti neresidir?" → "Ankara'dır." yeterlidir; arkasına Ankara'nın nüfusunu yazmayın.

## Satır formatı (JSONL)

Her satır tek bir JSON nesnesi:

```json
{"instruction":"Kullanıcı sorusu veya görev","input":"","output":"İstenen doğru cevap"}
```

| Alan | Açıklama |
|------|----------|
| `instruction` | Soru / komut (Türkçe tercih; kısa ve net) |
| `input` | Çoğu satırda `""`. Ek bağlam varsa buraya (ör. metin özeti) |
| `output` | Modelin üretmesi gereken cevap — **doğru, kısa, Türkçe** |

### Kurallar

1. Bir satır = bir örnek. Virgülle satır birleştirme yok.
2. `output` halüsinasyon içermesin (başkent = Ankara, 2+2 = 4).
3. Bu proje sorularında gerçek stack bilgisi kullan (gateway `:8080`, MLC Docker, JWT, soft PEFT).
4. UTF-8 kaydet; Windows’ta BOM ekleme.
5. Eğitim öncesi: https://huggingface.co/google/gemma-2b-it lisansını kabul et (gated).

### Örnek

```json
{"instruction":"Türkiye'nin başkenti neresidir?","input":"","output":"Ankara."}
```

## Hedef boyut

- Minimum anlamlı LoRA: **~100** satır
- İdeal: **200–300** satır
- `seed_examples.jsonl`’i kopyalayıp çeşitlendirerek `train.jsonl`’e ekleyebilirsin

## Colab’da kullanım

```python
from datasets import load_dataset
ds = load_dataset("json", data_files="train.jsonl", split="train")
```

Gemma chat template ile formatlama notebook’ta yapılır (`<start_of_turn>user` …).
