# MVP — Kapsam ve 2 Günlük Plan
**Teslim:** 21 Temmuz 2026 · **Bugün:** 19 Temmuz · **Strateji:** Önce canlıya al, sonra zenginleştir.

---

## 1. MVP İlkesi

Süre 2 gün. Bu yüzden tek kural var: **her fazın sonunda ürün canlıda çalışır durumda olmalı.** Hiçbir faz, bir önceki canlı durumu bozarak bitmez. Zaman biterse elinde her zaman gösterilebilir bir şey olur.

## 2. Kapsam İçi (MVP'de OLACAK)

| Alan | MVP kapsamı |
|---|---|
| Frontend | 3 master view: Auth, Inference, Dashboard (subview'larıyla) |
| WebLLM | Tek model (gemma-2-2b-it-q4f16_1-MLC), streaming chat, progress bar, WebGPU kontrolü |
| Metrikler | TTFT, tok/s, token sayıları, toplam süre, model yükleme süresi |
| Scoring | Kural tabanlı: latency + length + format → composite + accept/review/reject |
| Backend | 20 endpoint (PRD §6 tablosu birebir) |
| Auth | JWT access+refresh, bcrypt |
| DB | Render PostgreSQL |
| Deploy | Vercel (FE) + Render (BE+DB), MCP üzerinden |
| Doküman | README (mimari, endpoint tablosu, canlı linkler, MCP kanıtı) |

## 3. Kapsam Dışı (MVP'de OLMAYACAK — sakın başlama)

- Çoklu model karşılaştırma ekranı
- LLM-as-judge scoring (kural tabanlı yeterli)
- Email doğrulama / şifre sıfırlama maili
- Karanlık/aydınlık tema, animasyonlar, tasarım cilası
- Websocket / gerçek zamanlı çoklu kullanıcı
- Test coverage hedefi (sadece kritik akışa smoke test)
- Mobil optimizasyon (WebGPU mobilde zaten sorunlu)

## 4. Kabul Kriterleri (teslimde tek tek işaretle)

- [ ] `https://<proje>.vercel.app` açılıyor
- [ ] `https://<backend>.onrender.com/api/v1/healthz` → 200
- [ ] Register + login çalışıyor, token yenileme çalışıyor
- [ ] Chrome'da model iniyor (progress görünür), chat stream cevap veriyor
- [ ] Chat sırasında canlı metrik paneli güncelleniyor
- [ ] Cevap bitince skor kartı görünüyor (composite + karar)
- [ ] Mesaj+metrik+skor DB'ye yazılıyor (dashboard'da görünüyor)
- [ ] Dashboard: oturum listesi, oturum detayı, özet grafik
- [ ] README'de 20 endpoint tablosu + canlı linkler + MCP kanıt görselleri
- [ ] MF Academy MCP: bağlandıysa kanıt, bağlanamadıysa denedim-notu

## 5. Saat Bazlı Plan

### GÜN 1 — 19/20 Temmuz (iskelet + canlı deploy)

**Faz 0 — Kurulum + Spike (2–3 saat) [EN KRİTİK]**
- Ortam: Node 20+, Go 1.22+, Git, GitHub repo (monorepo: `/frontend`, `/backend`)
- Agent aracını kur (Claude Code önerilir — AGENT_PLAYBOOK'a bak)
- **Spike:** Boş bir Next.js sayfasında WebLLM ile Gemma'yı çalıştır. Amaç sadece "cevap geldi mi?"
- ⛔ Spike çalışmadan başka hiçbir işe geçme. Çalışmazsa: farklı model varyantı → farklı tarayıcı → GPU sürücüsü.
- MF Academy'ye MCP bilgisi için mesaj at (paralel, bekleme).

**Faz 1 — Go backend çekirdeği (3–4 saat)**
- Gin + GORM + Postgres bağlantısı, healthz + version + config[2] → **önce 5 endpoint**
- Auth 8 endpoint (JWT middleware dahil)
- Local'de curl ile smoke test

**Faz 2 — İlk deploy (2 saat)**
- Render MCP ile: Postgres oluştur + backend web service deploy → `/healthz` canlıda 200
- Next.js boş iskelet (3 route + layout) → Vercel MCP ile deploy
- CORS ayarı, FE→BE bağlantı testi (config endpoint'ini FE'den çağır)
- 🎯 Gün 1 sonu hedefi: **İki URL de canlı, auth uçtan uca çalışıyor.**

### GÜN 2 — 20/21 Temmuz (ürünleştirme)

**Faz 3 — Inference view (3–4 saat)**
- Spike kodunu View 2'ye taşı: model seçici, progress, streaming chat
- Metrik yakalama (TTFT, tok/s, tokenlar) + canlı panel
- Scoring fonksiyonu + skor kartı

**Faz 4 — LLM endpoint'leri + Dashboard (3–4 saat)**
- Backend: sessions/messages/scores/summary endpoint'leri (8 adet) → deploy
- FE: chat verilerini backend'e kaydet
- Dashboard: oturum listesi, detay, özet grafik (Recharts)

**Faz 5 — Teslim paketi (2 saat)**
- Uçtan uca test: temiz tarayıcıda register→chat→dashboard
- README yaz (endpoint tablosu, mimari, linkler, MCP ekran görüntüleri)
- Render'ı uyandır, son kontrol, teslim et

## 6. B Planları

| Sorun | B planı |
|---|---|
| WebLLM hiç çalışmadı (Faz 0) | Aynı UI + metrik + scoring mimarisini koru; inference'ı geçici olarak backend proxy'li ücretsiz bir API'ye bağla, README'ye "WebGPU cihaz kısıtı" notu düş. Mimari ve 20 EP aynen kalır. |
| Süre yetmiyor (Gün 2 öğlen) | Dashboard'ı tek subview'a indir (sadece oturum listesi+detay), grafikleri at |
| Render Postgres sorunlu | SQLite + Render persistent disk'e geç (GORM'da tek satır değişiklik) |
| MF Academy MCP cevap yok | README'ye iletişim denemesinin kanıtını koy, diğer 2 MCP kanıtını güçlendir |
