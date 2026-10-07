# trafikjam

Belirli bir koordinattaki trafiği periyodik olarak TomTom Traffic API ile kontrol eder,
her kontrolde Telegram'dan durumu (akıcı/yoğun/sıkışık) bildirir.

## Kurulum
```
pip install -r requirements.txt
cp .env.example .env   # değerleri doldur
python trafikjam.py --once   # tek ölçüm, bildirim göndermez
python trafikjam.py          # sürekli çalış
```

## Nasıl çalışır
- `güncel hız / serbest akış hızı` oranı hesaplanır: `< 0.40` sıkışık, `< 0.70` yoğunlaşıyor, aksi halde akıcı.
- Her kontrolde (varsayılan 5 dk) oranına bakılmaksızın Telegram'a durum mesajı gönderilir. Telegram hatası arayüzde görünür.
- API hatası olursa log'lanır ve bir sonraki periyotta tekrar denenir.

Test: `pytest`

## Web arayüzü (haritadan konum seçimi)
`python web.py` çalıştırıp `http://localhost:8000` adresini aç (`ADMIN_PASSWORD` ile basic auth; kullanıcı adı önemsiz).
Haritaya tıkla, isteğe bağlı bir ad yaz, **Bu noktayı izle**'ye bas. Konum `STATE_PATH` dosyasına
kaydedilir ve hemen ölçülür; sayfa mevcut durumu (hız, gecikme, son ölçüm) 30 sn'de bir yeniler.
**Bildirim saatleri:** panelde "Bildirim saatleri" bölümünden başlangıç/bitiş saati ve günleri seçip kaydet
(ör. 07:00–10:00, Pzt–Cum). Aralık dışında ölçüm de mesaj da yapılmaz, TomTom kotası harcanmaz.
Gece aşan aralık (22:00–06:00) olur; "Her zaman" ile sınırı kaldırırsın. Saat dilimi `TIMEZONE` (varsayılan `Europe/Istanbul`).
Başlangıç değerleri `NOTIFY_START`, `NOTIFY_END`, `NOTIFY_DAYS` env'leriyle de verilebilir; arayüzden kaydedilen değer onları geçersiz kılar.
Konum seçilmemişse izleme başlamaz. `TRAFIK_LAT/LON` env değerleri yalnızca başlangıç noktasıdır.

## Dokploy ile yayınlama
1. Dokploy'da **Application** oluştur, bu repoyu ve branch'i bağla.
2. Build Type: **Dockerfile** (yol: `Dockerfile`).
3. **Environment**: `ADMIN_PASSWORD`, `TOMTOM_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` zorunlu.
4. **Advanced → Volumes**: bir volume'ü `/data` yoluna bağla (seçilen konum redeploy'da kaybolmasın).
5. **Domains**: domain ekle, container port `8000`, HTTPS'i aç (şifre açık metin gitmesin).
6. Deploy et, domain'i aç, haritadan noktayı seç. Logs'ta `... akici (xx/yy km/s)` satırları görünür.

### Docker Compose ile
`docker-compose.yml` hazır. Dokploy'da **Compose** servisi oluşturup repoyu bağla (Compose Type: Docker Compose),
Environment sekmesine yukarıdaki değişkenleri gir, **Domains** kısmında servis `trafikjam`, port `8000` seç.
`/data` volume'ü (`trafikjam-data`) compose içinde tanımlı, ayrıca eklemen gerekmez.
Yerelde denemek için `.env` doldurup `docker compose up -d --build`; port yayınlamadığı için
yerelde bakmak istersen `ports: ["8000:8000"]` ekle.
