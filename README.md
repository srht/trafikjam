# trafikjam

Belirli bir koordinattaki trafiği periyodik olarak TomTom Traffic API ile kontrol eder,
durum değişince (akıcı → yoğun vb.) Telegram'dan haber verir.

## Kurulum
```
pip install -r requirements.txt
cp .env.example .env   # değerleri doldur
python trafikjam.py --once   # tek ölçüm, bildirim göndermez
python trafikjam.py          # sürekli çalış
```

## Nasıl çalışır
- `güncel hız / serbest akış hızı` oranı hesaplanır: `< 0.40` sıkışık, `< 0.70` yoğunlaşıyor, aksi halde akıcı.
- İlk ölçümde (başlangıç veya konum değişimi) her zaman, sonra yalnızca durum değiştiğinde bildirim atılır. Telegram hatası arayüzde görünür ve sonraki periyotta tekrar denenir.
- API hatası olursa log'lanır ve bir sonraki periyotta tekrar denenir.

Test: `pytest`

## Web arayüzü (haritadan konum seçimi)
`python web.py` çalıştırıp `http://localhost:8000` adresini aç (`ADMIN_PASSWORD` ile basic auth; kullanıcı adı önemsiz).
Haritaya tıkla, isteğe bağlı bir ad yaz, **Bu noktayı izle**'ye bas. Konum `STATE_PATH` dosyasına
kaydedilir ve hemen ölçülür; sayfa mevcut durumu (hız, gecikme, son ölçüm) 30 sn'de bir yeniler.
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
