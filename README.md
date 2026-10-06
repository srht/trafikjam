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
