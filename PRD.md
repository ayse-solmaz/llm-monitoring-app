# PRD — Raw LLM Monitoring & Decision Scoring App
**Versiyon:** 1.0 · **Tarih:** 19 Temmuz 2026 · **Teslim:** 21 Temmuz 2026 · **Geliştirici:** Tek kişi + AI agent'lar

---

## 1. Özet ve Vizyon

Tarayıcı içinde (client-side, WebGPU üzerinden) çalışan bir Gemma modelini kullanan, bu modelin ham performans metriklerini toplayan ve model cevaplarını puanlayan (decision scoring) bir web uygulaması.

**Temel değer önerisi:** LLM sunucuda değil, kullanıcının tarayıcısında çalışır (MLC-LLM / WebLLM). Uygulama bu çalışmayı canlı izler: token hızı, ilk token süresi, bellek, ve her cevabın kalite/karar skorları. Tüm veriler Go backend'e kaydedilir ve dashboard'da görselleştirilir.

**Projenin asıl öğrenme hedefi:** MLC-LLM / WebLLM teknolojisini öğrenmek ve çalışır halde göstermek. Diğer her şey bu çekirdeği destekleyen iskelettir.

---

## 2. Zorunlu Gereksinimler (Ödevden Gelen)

| # | Gereksinim | Detay |
|---|---|---|
| R1 | Next.js Single Page App | Min. 3 master view + subview'lar |
| R2 | Auth | Master view'lardan biri; login/register akışı |
| R3 | Web LLM | Gemma modeli, MLC-LLM (WebLLM) ile tarayıcıda inference |
| R4 | Vercel deployment | Frontend canlı olacak |
| R5 | Go backend | Minimum 20 endpoint |
| R6 | Render deployment | Backend canlı olacak ("live live live") |
| R7 | MCP kullanımı | Render MCP + Vercel MCP + MF Academy MCP |
| R8 | App base-case | Raw LLM Monitoring + Decision Scoring |
| R9 | Endpoint dağılımı | Config[2] + Auth[8] + WEB MLC-LLM[6–8] + CMN |

---

## 3. Kullanıcılar ve Senaryolar

**Persona:** LLM performansını incelemek isteyen geliştirici/öğrenci.

**Ana akış (happy path):**
1. Kullanıcı siteye girer → kayıt olur / giriş yapar.
2. Chat ekranına gider → model tarayıcıya indirilir (progress bar görünür).
3. Prompt yazar → cevap stream edilir; aynı anda TTFT, tok/s, token sayıları ölçülür.
4. Cevap bittiğinde otomatik decision scoring çalışır → skorlar backend'e kaydedilir.
5. Dashboard'da geçmiş oturumların metrik ve skorlarını grafiklerle inceler.

---

## 4. Master Views ve Subviews (R1, R2)

### View 1 — Auth
- **Subview 1a:** Login formu
- **Subview 1b:** Register formu
- **Subview 1c:** Profil / hesap (me bilgisi, şifre değiştirme, logout)

### View 2 — Inference (Chat + Live Monitoring)
- **Subview 2a:** Model seçici + yükleme durumu (indirme progress'i, WebGPU uyumluluk kontrolü)
- **Subview 2b:** Chat arayüzü (streaming cevap)
- **Subview 2c:** Canlı metrik paneli (TTFT, tokens/sec, prompt/completion token, elapsed time — cevap akarken güncellenir)

### View 3 — Dashboard (Monitoring & Scoring)
- **Subview 3a:** Oturum listesi (geçmiş chat oturumları)
- **Subview 3b:** Oturum detayı (mesajlar + her mesajın metrikleri ve skorları)
- **Subview 3c:** Özet grafikler (ortalama tok/s, skor dağılımı, zaman içinde trend)

SPA yapısı: Next.js App Router, tüm view'lar tek sayfa deneyimi içinde client-side geçişle (route değişimi full reload yapmaz).

---

## 5. WebLLM / MLC-LLM Entegrasyonu (R3, R8)

- **Kütüphane:** `@mlc-ai/web-llm` (npm)
- **Model:** `gemma-2-2b-it-q4f16_1-MLC` (prebuilt listeden; cihaz zayıfsa fallback: daha küçük quantize varyant)
- **Gereksinim:** WebGPU destekli tarayıcı (Chrome/Edge). Desteklenmiyorsa kullanıcıya açık uyarı + desteklenen tarayıcı listesi göster.
- **Model yükleme:** `CreateMLCEngine` ile, `initProgressCallback` progress bar'a bağlanır.
- **Inference:** `engine.chat.completions.create({ stream: true })` — OpenAI-uyumlu API.

### Toplanacak ham metrikler (Raw LLM Monitoring)
| Metrik | Kaynak |
|---|---|
| TTFT (ilk token süresi, ms) | İstek başlangıcı → ilk chunk zamanı |
| Decode hızı (tokens/sec) | WebLLM `runtimeStatsText()` / chunk sayımı |
| Prompt token sayısı | usage bilgisi |
| Completion token sayısı | usage bilgisi |
| Toplam süre (ms) | İstek başlangıcı → bitiş |
| Model yükleme süresi (ms) | Engine init süresi |
| Model adı + quantizasyon | Config |
| Tarayıcı/GPU bilgisi | `navigator.userAgent`, WebGPU adapter info |

### Decision Scoring (R8)
Her tamamlanan cevap için 0–100 arası skorlar hesaplanır ve kaydedilir:
- **Latency score:** TTFT ve tok/s eşiklerine göre (ör. TTFT<1s ve >15 tok/s → yüksek)
- **Length score:** Cevap uzunluğunun prompt'a oranı (çok kısa/çok uzun cezalandırılır)
- **Format score:** Cevabın yapısal sağlığı (boş değil, yarıda kesilmemiş, tekrar oranı düşük)
- **Composite decision score:** Ağırlıklı ortalama → "accept / review / reject" kararı

Skorlama v1'de deterministik (kural tabanlı, client-side hesap) — LLM-as-judge sonraki sürüm.

---

## 6. Go Backend — 20 Endpoint (R5, R9)

- **Stack:** Go 1.22+, Gin framework, GORM, PostgreSQL (Render managed Postgres), JWT (access+refresh)
- **Prefix:** `/api/v1`

### Config [2]
| # | Method | Path | Açıklama |
|---|---|---|---|
| 1 | GET | /config | App konfigürasyonu (feature flag'ler, skor eşikleri, versiyon) |
| 2 | GET | /config/models | Desteklenen model listesi (id, boyut, önerilen cihaz) |

### Auth [8]
| # | Method | Path | Açıklama |
|---|---|---|---|
| 3 | POST | /auth/register | Kayıt (email+şifre, bcrypt hash) |
| 4 | POST | /auth/login | Giriş → access + refresh token |
| 5 | POST | /auth/refresh | Refresh token ile yeni access token |
| 6 | POST | /auth/logout | Refresh token'ı geçersiz kıl |
| 7 | GET | /auth/me | Oturum sahibinin bilgisi (JWT korumalı) |
| 8 | PUT | /auth/me | Profil güncelle (isim vb.) |
| 9 | POST | /auth/change-password | Şifre değiştir |
| 10 | DELETE | /auth/me | Hesabı sil |

### WEB MLC-LLM [8]
| # | Method | Path | Açıklama |
|---|---|---|---|
| 11 | POST | /llm/sessions | Yeni chat oturumu aç (model adı, cihaz bilgisi) |
| 12 | GET | /llm/sessions | Kullanıcının oturum listesi (sayfalı) |
| 13 | GET | /llm/sessions/:id | Oturum detayı (mesajlar+metrikler+skorlar) |
| 14 | DELETE | /llm/sessions/:id | Oturumu sil |
| 15 | POST | /llm/sessions/:id/messages | Mesaj + ham metrikleri kaydet |
| 16 | POST | /llm/sessions/:id/scores | Bir mesajın decision skorlarını kaydet |
| 17 | GET | /llm/metrics/summary | Kullanıcının özet istatistikleri (ort. tok/s, ort. TTFT, toplam token) |
| 18 | GET | /llm/scores/summary | Skor dağılımı ve accept/review/reject sayıları |

### CMN [2]
| # | Method | Path | Açıklama |
|---|---|---|---|
| 19 | GET | /healthz | Sağlık kontrolü (Render health check bunu kullanır) |
| 20 | GET | /version | Build versiyonu + commit hash |

**Toplam: 20 endpoint** (Config 2 + Auth 8 + LLM 8 + CMN 2). Zaman kalırsa eklenebilir: GET /llm/models/leaderboard, POST /feedback.

### Veri modeli
- **users:** id, email, password_hash, name, created_at
- **refresh_tokens:** id, user_id, token_hash, expires_at, revoked
- **sessions:** id, user_id, model_id, device_info, model_load_ms, created_at
- **messages:** id, session_id, role, content, ttft_ms, tokens_prompt, tokens_completion, tokens_per_sec, total_ms, created_at
- **scores:** id, message_id, latency_score, length_score, format_score, composite, decision(enum), created_at

---

## 7. Deployment (R4, R6)

| Bileşen | Platform | Not |
|---|---|---|
| Frontend (Next.js) | Vercel | GitHub repo bağla → otomatik deploy. Env: `NEXT_PUBLIC_API_URL` |
| Backend (Go) | Render Web Service | Dockerfile ile. Health check: `/healthz`. Env: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGIN` |
| Database | Render PostgreSQL (free) | Backend ile aynı region |

**Dikkat:** Render free tier'da servis inaktivitede uyur; ilk istek 30–60 sn sürebilir. Sunum/teslim öncesi servisi uyandır. CORS: backend, Vercel domain'ine izin vermeli.

---

## 8. MCP Kullanımı (R7)

MCP (Model Context Protocol): AI agent'ların dış servisleri araç olarak kullanmasını sağlayan protokol. Bu projede deploy ve yönetim işlemleri agent üzerinden MCP ile yapılacak:

- **Render MCP:** Backend servisini oluşturma, deploy tetikleme, log okuma — agent'a Render MCP server bağlanır.
- **Vercel MCP:** Frontend deploy, domain/env yönetimi.
- **MF Academy MCP:** Ödevi veren kurumun MCP'si — **bağlantı bilgisi/dokümanı kurumdan istenecek.** (Muhtemelen teslim/doğrulama için.)

Kanıt olarak: agent oturumlarında MCP araç çağrılarının ekran görüntüleri/logları saklanacak (teslimde "MCP kullandım" kanıtı).

---

## 9. Fonksiyonel Olmayan Gereksinimler

- **Güvenlik:** bcrypt şifre hash, JWT expiry (access 15 dk, refresh 7 gün), CORS whitelist, rate limit (basit, memory-based)
- **Performans:** Dashboard sorguları sayfalı; metrik kaydı fire-and-forget (chat akışını bloklamaz)
- **Uyumluluk:** WebGPU yoksa graceful degradation — uygulama açılır, chat devre dışı, açıklayıcı mesaj görünür (dashboard yine çalışır)
- **Gözlemlenebilirlik:** Backend structured log (JSON), her istekte request-id

---

## 10. Başarı Kriterleri (Definition of Done)

1. ✅ Vercel URL'i açılıyor, 3 master view gezilebiliyor
2. ✅ Register → login → korumalı sayfaya erişim çalışıyor
3. ✅ Chrome'da Gemma modeli iniyor ve chat cevap veriyor (stream)
4. ✅ Cevap sırasında canlı metrikler görünüyor; bitince skorlar hesaplanıyor
5. ✅ Metrik + skorlar Render'daki backend'e kaydediliyor; dashboard'da listeleniyor
6. ✅ Render'daki `/healthz` 200 dönüyor; 20 endpoint dokümante (README'de tablo)
7. ✅ Render MCP + Vercel MCP kullanım kanıtı mevcut
8. ✅ README: mimari şema, kurulum, endpoint listesi, canlı linkler

---

## 11. Riskler ve Önlemler

| Risk | Olasılık | Önlem |
|---|---|---|
| WebGPU cihazda çalışmaz | Orta | İlk saatte spike testi; küçük model fallback; sunumu Chrome'da yap |
| Model indirme çok yavaş | Orta | 2B model seç; sunum öncesi cache'le (bir kez indir) |
| Render cold start | Yüksek | Teslim öncesi uyandır; README'ye not düş |
| 2 günlük süre | Yüksek | MVP.md'deki kesin sıralamaya uy; "nice-to-have" hiçbir şeye başlama |
| MF Academy MCP belirsiz | Yüksek | Bugün kuruma yaz, bilgi gelmezse README'de "beklemede" olarak belgele |
| Agent halüsinasyonu | Orta | Her fazda canlıda elle test; AGENT_PLAYBOOK'taki DoD kontrolleri |
