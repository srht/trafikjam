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
- Spam olmaması için yalnızca durum değiştiğinde bildirim atılır.
- API hatası olursa log'lanır ve bir sonraki periyotta tekrar denenir.

Test: `pytest`

## Dokploy ile yayınlama
1. Dokploy'da **Application** oluştur, bu repoyu ve branch'i bağla.
2. Build Type: **Dockerfile** (yol: `Dockerfile`).
3. **Environment** sekmesine `.env.example` içindeki değişkenleri gir
   (`TRAFIK_LAT`, `TRAFIK_LON`, `TOMTOM_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` zorunlu).
4. Domain/port tanımlama, bu servis HTTP sunmaz; sadece arka planda çalışır.
5. Deploy et, **Logs** sekmesinde `... akici (xx/yy km/s)` satırlarını görmelisin.
