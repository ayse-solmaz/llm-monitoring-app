Sistem mimarisinin zirvesine hoş geldin. Bu doküman, tüm bileşenlerin bir araya geldiği ve yerel yapay zeka gücünün modern web teknolojileriyle birleştiği **Stage Out Three: FINAL BOSS** aşamasının nihai ürün spesifikasyonudur (Product Spec).

Aşağıda, talep ettiğin 4 ana fazın zengin Markdown formatında yapılandırılmış mimari dökümünü bulabilirsin.

---

## 🛠️ Mimari Teknoloji Özeti (Tech Stack)

| Bileşen | Teknoloji / Yaklaşım | Görev |
| --- | --- | --- |
| **LLM Motoru** | MLC-LLM / Docker | Modeli yerel donanımda (GPU/CPU) hızlandırılmış olarak çalıştırma |
| **Optimizasyon** | PEFT (LoRA/QLoRA) | Düşük kaynakla modele spesifik yetenekler kazandırma |
| **Backend (B)** | Go (Golang) | Yüksek performanslı API, MCP sunucusu ve veritabanı yönetimi |
| **Frontend (F)** | TypeScript / React | WebMCP entegrasyonu, kullanıcı arayüzü ve Admin Paneli |
| **İletişim** | Model Context Protocol (MCP) | Frontend ve Backend LLM arasındaki standardize edilmiş veri akışı |

---

## 1. MLC - LLM Render & Local Docker Run

FINAL BOSS aşamasında dışa bağımlılık yoktur. Model tamamen izole bir ortamda, donanım ivmeli (Vulkan/CUDA/Metal) olarak çalışır.

### Docker Konfigürasyonu

Sistemi tek tuşla ayağa kaldırmak için gereken standart kapsayıcı (container) yapısı:

```yaml
version: '3.8'
services:
  llm-engine:
    image: ghcr.io/mlc-ai/mlc-llm:latest
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    ports:
      - "8000:8000"
    volumes:
      - ./models:/models
      - ./peft-adapters:/adapters
    command: >
      mlc_llm serve /models/FinalBoss-7B-q4f16_1
      --model-lib-path /models/FinalBoss-7B/lib.so

```

> **Önemli Not:** Docker üzerinden veya doğrudan yerel derleme ile (MLC CLI) render alarak modelin API uçlarını (REST/WebSocket) hazır hale getiriyoruz.

---

## 2. PEFT Teknikleri ve MCP Entegrasyonu

Modelin büyük ağırlıklarını değiştirmek yerine, **PEFT (Parameter-Efficient Fine-Tuning)** kullanarak adaptörler (LoRA) yüklüyoruz. Bu, sistemi dinamik kılar.

### Model Context Protocol (MCP) Yapısı

Frontend ve Backend'in LLM ile nasıl konuştuğunun haritası:

* **F[.ts] (Frontend - WebMCP):** TypeScript tabanlı istemci. Kullanıcıdan gelen "Deepkwiki" aramalarını alır, statik spesifikasyonları derler ve MCP formatında paketler.
* **B[.go] (Backend - Go):** Go tabanlı sunucu. WebMCP'den gelen talepleri alır, yetki kontrolü yapar ve MLC-LLM motoruna iletir.

```go
// Go Backend: Örnek MCP İstek Karşılayıcı
func HandleMCPRequest(ctx context.Context, req MCPPayload) (RichResult, error) {
    // 1. Validasyon
    // 2. PEFT adaptörünü dinamik seçme
    // 3. MLC-LLM API'sine proxy atma
    // 4. Sonucu zenginleştirme (Rich Formatting)
}

```

---

## 3. System Core (SC): Kullanıcı Akışı ve DeepKwiki

Burası uygulamanın kalbidir. Kullanıcı girişinden, zengin sonuçların (Rich Result) ekrana yansıtılmasına kadar geçen süreç sıkı bir güvenlik ve performans standartına bağlıdır.

1. **Kullanıcı Girişi (Login / Auth):**
Kullanıcı kimlik doğrulaması Go backend üzerinden JWT (JSON Web Token) ile sağlanır. Statik spesifikasyonlar (kullanıcı rolleri) doğrulanır.


2. **Web Çağrısı (DeepKwiki Request):**
Kullanıcı arayüzden sorguyu yapar. TypeScript (WebMCP) sorguyu zenginleştirir ve Go backend'e iletir.


3. **LLM İşleme (Backend Bases LLM):**
Go sunucusu, seçili PEFT adaptörüyle birlikte MLC-LLM'e sorguyu gönderir. Model, yerel Docker üzerinde render alıp yanıt üretir.


4. **Zengin Sonuç (Rich Result) Sunumu:**
Gelen ham metin, Frontend tarafından ayrıştırılır. Tablolar, grafikler ve Markdown elementleri içeren dinamik, zengin bir UI bileşenine dönüştürülür.

**Grafik formatı (assistant mesajı):** fenced code block dili `chart`, gövde JSON:

```chart
{
  "type": "line",
  "title": "Optional title",
  "xKey": "step",
  "yKey": "tps",
  "data": [{ "step": "1", "tps": 8.2 }]
}
```

`type`: `line` | `bar`. `xKey` / `yKey` varsayılan: `name` / `value`. Önizleme: `/rich-preview`.


---

## 4. Admin User LLM Modify Panel

FINAL BOSS'u kontrol eden yöneticinin (Admin) kokpitidir. Arayüz (TypeScript/React) üzerinden modele canlı müdahale edilmesini sağlar.

### Panel Yetenekleri

| Modül | İşlev |
| --- | --- |
| **Adapter Yönetimi** | Farklı PEFT (LoRA) dosyalarını tek tıkla yükleme/kaldırma |
| **Sistem Prompları** | LLM'in temel karakterini (System Prompt) canlı düzenleme |
| **Context Limitleri** | Maksimum token, sıcaklık (temperature) ve Top-P ayarları |
| **Log Monitörü** | Go Backend üzerinden akan sorguları ve gecikmeleri (latency) izleme |

Bu panel sayesinde, modeli yeniden başlatmadan (Hot-Swap) davranışını tamamen değiştirebilir, kurumsal veya spesifik bir amaca göre (örneğin sadece kod yazan bir asistan veya DeepKwiki bilgi bankası) anında modifiye edebilirsin.

---

## Implementation map (this repo)

See **[FINAL_BOSS_STATUS.md](./FINAL_BOSS_STATUS.md)** for Done / Soft / Hardware-blocked.

- Live inference: browser WebMCP → `mlc-gateway` → nginx → MLC (CPU by default).
- Go `HandleMCPRequest`: `backend/internal/application/mcp` (internal; no new PRD HTTP path).
- Soft PEFT hot-swap: Admin `/admin` → next Chat message.
- GPU overlay: `docker-compose.gpu.yml` (optional; requires local CUDA image).
