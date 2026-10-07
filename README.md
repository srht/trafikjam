# trafikjam

Kullanıcıların kayıt olup haritadan izlemek istedikleri yolları seçtiği, her noktanın trafiğini
TomTom Traffic API ile periyodik ölçüp sahibine Telegram'dan bildiren web uygulaması.

- Kullanıcı adı + şifreyle kayıt/giriş. Herkes yalnızca **kendi** noktalarını görür ve yönetir.
- Her kullanıcı kendi Telegram chat id'sini girer; bildirimler kendi chat'ine gider (panelde "Test" butonu var).
- Her nokta için ayrı bildirim saat aralığı ve gün seçimi. Aralık dışında ölçüm de mesaj da yapılmaz.
- Her ölçümde (varsayılan 5 dk) trafik oranına bakılmaksızın durum mesajı gönderilir.
- Sınıflandırma: `güncel hız / serbest akış hızı` `< 0.40` sıkışık, `< 0.70` yoğunlaşıyor, aksi halde akıcı.

## Yerelde çalıştırma
```
pip install -r requirements.txt
cp .env.example .env   # TOMTOM_API_KEY, TELEGRAM_BOT_TOKEN doldur; yerelde COOKIE_SECURE=0 yap
python web.py          # http://localhost:8000
pytest
```

## Güvenlik notları
- Şifreler hash'li saklanır (werkzeug), oturum imzalı HttpOnly/SameSite çerezdir; HTTPS arkasında `Secure` işaretlenir.
- Çok sayıda hatalı girişte 15 dk bloklanır; kayıt IP başına saatte 10 denemeyle sınırlıdır.
- **Kayıt varsayılan olarak herkese açıktır.** TomTom kotası tüm kullanıcılar arasında ortaktır;
  yalnızca tanıdıklarının kullanması için `REGISTRATION_CODE` ayarla (davet kodu sorulur),
  kullanıcı başı nokta limitini `MAX_POINTS_PER_USER` ile sınırla.
- Kota hesabı: toplam nokta × (86400 / `CHECK_INTERVAL_SECONDS`) ≤ ~2500/gün (ücretsiz katman).

## Dokploy ile yayınlama
**Dockerfile ile:** Application oluştur, repoyu ve `main` branch'ini bağla, Build Type: Dockerfile.
**Compose ile:** Compose servisi oluştur (Docker Compose), aynı repo/branch.

1. Environment: `TOMTOM_API_KEY`, `TELEGRAM_BOT_TOKEN` zorunlu; önerilen: `REGISTRATION_CODE`.
2. Dockerfile ile kurarsan Advanced → Volumes'te bir volume'ü `/data`'ya bağla (veritabanı ve oturum anahtarı burada;
   compose'ta `trafikjam-data` hazır tanımlı).
3. Domains: domain ekle, container port `8000`, HTTPS açık.
4. Deploy et, domain'i aç, kayıt ol, Telegram chat id'ni gir, haritadan nokta ekle.

> Eski tek kullanıcılı sürümden geçiş: `ADMIN_PASSWORD`, `TRAFIK_LAT/LON/NAME`, `NOTIFY_*`, `STATE_PATH` artık kullanılmıyor,
> eski `state.json`'daki nokta taşınmaz; kayıt olup noktayı yeniden ekle.
