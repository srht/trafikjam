"""Çekirdek: ayarlar, TomTom trafik verisi, Telegram gönderimi, bildirim saat aralığı."""
import logging
import os
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

TOMTOM_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"

AKICI, ORTA, YOGUN, KAPALI = "akici", "orta", "yogun", "kapali"
EMOJI = {AKICI: "🟢", ORTA: "🟡", YOGUN: "🔴", KAPALI: "⛔"}
ETIKET = {AKICI: "Trafik akıcı", ORTA: "Trafik yoğunlaşıyor", YOGUN: "Trafik sıkışık", KAPALI: "Yol kapalı"}
ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)  # 0 = Pazartesi

log = logging.getLogger("trafikjam")


@dataclass
class Settings:
    tomtom_key: str
    telegram_token: str
    secret_key: str = "test-secret"
    interval: int = 300
    yogun_esik: float = 0.40  # güncel hız / serbest akış hızı bunun altındaysa sıkışık
    orta_esik: float = 0.70
    timezone: str = "Europe/Istanbul"
    data_dir: str = "data"
    registration_code: str = ""  # doluysa kayıt için gerekli
    max_points: int = 5  # kullanıcı başına
    cookie_secure: bool | None = None  # None: isteğin HTTPS olup olmadığına göre otomatik

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "trafikjam.db")

    @classmethod
    def from_env(cls) -> "Settings":
        def need(k):
            v = os.environ.get(k)
            if not v:
                sys.exit(f"Eksik ortam değişkeni: {k} (bkz. .env.example)")
            return v

        data_dir = os.environ.get("DATA_DIR", "data")
        return cls(
            tomtom_key=need("TOMTOM_API_KEY"),
            telegram_token=need("TELEGRAM_BOT_TOKEN"),
            secret_key=os.environ.get("SECRET_KEY") or _persistent_secret(data_dir),
            interval=int(os.environ.get("CHECK_INTERVAL_SECONDS", "300")),
            yogun_esik=float(os.environ.get("YOGUN_ESIK", "0.40")),
            orta_esik=float(os.environ.get("ORTA_ESIK", "0.70")),
            timezone=os.environ.get("TIMEZONE", "Europe/Istanbul"),
            data_dir=data_dir,
            registration_code=os.environ.get("REGISTRATION_CODE", ""),
            max_points=int(os.environ.get("MAX_POINTS_PER_USER", "5")),
            cookie_secure={"1": True, "0": False}.get(os.environ.get("COOKIE_SECURE", "")),
        )


def _persistent_secret(data_dir: str) -> str:
    """SECRET_KEY verilmediyse bir kez üretip data dizininde saklar (oturumlar redeploy'da düşmesin)."""
    path = os.path.join(data_dir, "secret_key")
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        os.makedirs(data_dir, exist_ok=True)
        key = secrets.token_hex(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
        return key


@dataclass
class Flow:
    current_speed: float
    free_flow_speed: float
    current_time: int
    free_flow_time: int
    road_closure: bool


def fetch_flow(s: Settings, lat: float, lon: float) -> Flow:
    r = requests.get(
        TOMTOM_URL,
        params={"point": f"{lat},{lon}", "unit": "KMPH", "key": s.tomtom_key},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()["flowSegmentData"]
    return Flow(
        current_speed=d["currentSpeed"],
        free_flow_speed=d["freeFlowSpeed"],
        current_time=d["currentTravelTime"],
        free_flow_time=d["freeFlowTravelTime"],
        road_closure=bool(d.get("roadClosure", False)),
    )


def classify(flow: Flow, s: Settings) -> str:
    if flow.road_closure:
        return KAPALI
    if flow.free_flow_speed <= 0:
        return AKICI
    ratio = flow.current_speed / flow.free_flow_speed
    if ratio < s.yogun_esik:
        return YOGUN
    if ratio < s.orta_esik:
        return ORTA
    return AKICI


def format_message(name: str, lat: float, lon: float, level: str, flow: Flow) -> str:
    gecikme = max(0, flow.current_time - flow.free_flow_time)
    return (
        f"{EMOJI[level]} {ETIKET[level]} — {name or f'{lat:.4f},{lon:.4f}'}\n"
        f"Hız: {flow.current_speed:.0f} km/s (normalde {flow.free_flow_speed:.0f})\n"
        f"Ek gecikme: ~{gecikme // 60} dk\n"
        f"https://maps.google.com/?q={lat},{lon}"
    )


def send_telegram(token: str, chat_id: str, text: str) -> None:
    r = requests.post(
        TELEGRAM_URL.format(token=token),
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    if not r.ok:
        try:
            desc = r.json().get("description", "")
        except ValueError:
            desc = r.text[:100]
        raise RuntimeError(f"Telegram {r.status_code}: {desc}")


# --- bildirim saat aralığı -------------------------------------------------

def parse_days(v) -> tuple:
    """"0,1,2" veya [0,1,2] -> sıralı tuple; boş = her gün."""
    items = v.split(",") if isinstance(v, str) else v
    days = sorted({int(x) for x in items if str(x).strip() != ""})
    if any(d < 0 or d > 6 for d in days):
        raise ValueError("Gün değerleri 0-6 olmalı")
    return tuple(days) if days else ALL_DAYS


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ValueError("Geçersiz saat")
    return int(h) * 60 + int(m)


def validate_window(start: str, end: str) -> None:
    if bool(start) != bool(end):
        raise ValueError("Başlangıç ve bitiş saatinin ikisi de girilmeli (ya da ikisi de boş)")
    if not start:
        return
    try:
        a, b = _minutes(start), _minutes(end)
    except ValueError:
        raise ValueError("Saat HH:MM biçiminde olmalı") from None
    if a == b:
        raise ValueError("Başlangıç ve bitiş aynı olamaz")


def in_window(start: str, end: str, days: tuple, tz: str, now: datetime | None = None) -> bool:
    """Şu an bildirim aralığında mı? Gece aşan aralıkta gün, aralığın başladığı güne göre sayılır."""
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz))
    cur = now.hour * 60 + now.minute
    if not start:
        return now.weekday() in days
    a, b = _minutes(start), _minutes(end)
    if a < b:
        return a <= cur < b and now.weekday() in days
    if cur >= a:
        return now.weekday() in days
    if cur < b:
        return (now - timedelta(days=1)).weekday() in days
    return False
