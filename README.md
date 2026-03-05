# WhatsApp Online Tracker - Python

WhatsApp'ta takip ettiğiniz numaraların online olma durumlarını ve sürelerini gerçek zamanlı takip eden Python web uygulaması.

## 🎯 Özellikler

### Çalışan Özellikler:
- ✅ Gerçek WhatsApp Web entegrasyonu (Playwright)
- ✅ Numara ekleme/silme
- ✅ Otomatik online/offline durumu tespiti
- ✅ QR kod ile WhatsApp bağlantısı
- ✅ Online süresi kaydı
- ✅ Online zamanı kaydı
- ✅ Online geçmişi görüntüleme
- ✅ İstatistikler
- ✅ CSV/JSON dışa aktarım
- ✅ SQLite veritabanı
- ✅ Otomatik polling (3 saniyede bir kontrol)

## 📦 Kurulum

### 1. Gereksinimler
- Python 3.8+
- Chrome/Chromium tarayıcısı (Playwright otomatik indirir)

### 2. Dependencies Yükle
```bash
pip install -r requirements.txt
```

### 3. Playwright Browser İndir
```bash
playwright install chromium
```

### 4. Uygulamayı Çalıştır
```bash
python app.py
```

Uygulama `http://localhost:5000` adresinde açılacak.

## 📱 Kullanım

### WhatsApp'a Bağlanma
1. Uygulamayı açın
2. Sağ üstteki "WhatsApp'a Bağlan" butonuna tıklayın
3. Ekranda görüntülenen QR kodu taratın
4. Telefonunuzdaki WhatsApp uygulamasını açın
5. Ayarlar > Bağlı Cihazlar > Cihaz Bağla seçeneğini seçin
6. QR kodu taratın
7. Başarıyla bağlandıktan sonra numara eklemeye başlayabilirsiniz

### Numara Ekleme
1. Sağ alttaki + butonuna tıklayın
2. İsim ve telefon numarası girin (+905321234567)
3. Kaydet butonuna basın
4. WhatsApp'taki sohbet listesinde numaranın olduğundan emin olun

### Online Durumu Kontrol Etme
- Uygulama otomatik olarak 3 saniyede bir tüm numaraları kontrol eder
- Online durumları otomatik olarak güncellenir
- Manuel kontrol için her numara kartındaki WiFi ikonuna tıklayın

### İstatistikleri Görüntüleme
- Her numara kartında çubuk grafik ikonu vardır
- Bu ikona tıklayarak detaylı istatistikleri görebilirsiniz
- CSV/JSON olarak dışa aktarabilirsiniz

## 📊 Teknik Detaylar

### WhatsApp Web Entegrasyonu
Uygulama, Playwright kullanarak WhatsApp Web'i otomatik olarak açar ve kontrol eder:

1. **Chromium Browser**: Playwright, Chromium tarayıcısı başlatır
2. **QR Kod Entegrasyonu**: WhatsApp Web QR kodunu otomatik olarak alır
3. **DOM Manipülasyonu**: WhatsApp Web'in DOM yapısını analiz ederek online durumunu tespit eder
4. **Otomatik Polling**: Belirli aralıklarla otomatik olarak online durumlarını kontrol eder
5. **Veritabanı Entegrasyonu**: Tüm durumları SQLite veritabanına kaydeder

### Nasıl Çalışır?
```
1. Playwright başlat → WhatsApp Web aç
2. QR kod al → Kullanıcıya göster → Bağlan
3. Takip edilen numaralar için polling başlat
4. Her 3 saniyede bir online durumlarını kontrol et
5. Değişiklik varsa veritabanına kaydet
6. Frontend'e güncel verileri gönder
```

### Online Durum Tespiti
WhatsApp Web'in DOM yapısındaki şu elementleri analiz eder:
- `[data-id]` - Sohbet elementlerini bulur
- `[data-testid="last-seen"]` - Online durumunu tespit eder
- "çevrimiçi" veya "online" metnini arar

## 📂 Proje Yapısı

```
├── app.py                      # Flask uygulaması
├── models.py                   # SQLAlchemy modelleri
├── whatsapp_service.py         # WhatsApp servisi (Playwright)
├── requirements.txt            # Python dependencies
├── static/
│   ├── style.css              # CSS dosyaları
│   └── script.js              # JavaScript dosyaları
├── templates/
│   └── index.html             # Ana sayfa
└── whatsapp_tracker.db        # SQLite veritabanı (otomatik oluşturulur)
```

## 🔒 Güvenlik ve Gizlilik

- Veriler yerel SQLite veritabanında saklanır
- Kişisel veriler paylaşılmaz
- Playwright headless olmayan modda çalışır, hiçbir görsel kayıt tutulmaz

## ⚠️ Yasal ve Etik Notlar

- Bu uygulama eğitim ve demo amaçlıdır
- Gerçek WhatsApp online durumu takibi, WhatsApp'ın kullanım şartlarına aykırı olabilir
- Kişisel gizlilik haklarını ihlal etmeden kullanın
- Başkalarını izlemek için kullanmayın
- WhatsApp hesabınızın spam olarak işaretlenmemesi için dikkatli kullanın

## 🐛 Hata Ayıklama

```bash
# Logları görüntüle
python app.py

# Veritabanı sıfırla
rm whatsapp_tracker.db
python app.py
```

## 💡 İpuçları

- **Bağlantı Kalitesi**: İnternet bağlantınız stabil olmalıdır
- **Numara Formatı**: Telefon numaralarını +90 formatında girin
- **Sohbet Listesi**: Takip etmek istediğiniz numaralar WhatsApp Web'de görünülmelidir
- **Performans**: Çok sayıda numara takip etmek performansı etkileyebilir
- **Polling Aralığı**: Otomatik kontrol her 3 saniyede bir yapılır

## 🆘 Destek

Sorun bildirmek veya öneri yapmak için GitHub issues kullanın.

## ⚠️ Bilinen Sorunlar

- WhatsApp Web yapısı değiştiğinde tespit çalışmayabilir
- Bazı hesaplar için WhatsApp spam koruması devreye girebilir
- Çok sayıda numara takip edildiğinde Playwright performansı düşebilir

---

**Versiyon:** 1.0.0  
**Platform:** Web (Flask)  
**Entegrasyon:** Playwright  
**Durum:** Gerçek WhatsApp Web Entegrasyonu
