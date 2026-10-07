"""Belirli bir koordinattaki trafiği periyodik kontrol edip Telegram'dan haber verir."""
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

TOMTOM_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"

AKICI, ORTA, YOGUN, KAPALI = "akici", "orta", "yogun", "kapali"
EMOJI = {AKICI: "🟢", ORTA: "🟡", YOGUN: "🔴", KAPALI: "⛔"}
ETIKET = {AKICI: "Trafik akıcı", ORTA: "Trafik yoğunlaşıyor", YOGUN: "Trafik sıkışık", KAPALI: "Yol kapalı"}

log = logging.getLogger("trafikjam")


@dataclass
class Config:
    lat: float | None
    lon: float | None
    tomtom_key: str
    telegram_token: str
    telegram_chat_id: str
    interval: int = 300
    name: str = ""
    state_path: str = "data/state.json"
    yogun_esik: float = 0.40  # güncel hız / serbest akış hızı bunun altındaysa sıkışık
    orta_esik: float = 0.70
    # Bildirim saat aralığı ("HH:MM"); ikisi de boşsa her zaman aktif. Gece aşan aralık (22:00-06:00) desteklenir.
    window_start: str = ""
    window_end: str = ""
    days: tuple = (0, 1, 2, 3, 4, 5, 6)  # 0=Pazartesi
    timezone: str = "Europe/Istanbul"

    @classmethod
    def from_env(cls) -> "Config":
        def need(k):
            v = os.environ.get(k)
            if not v:
                sys.exit(f"Eksik ortam değişkeni: {k} (bkz. .env.example)")
            return v

        lat = float(os.environ["TRAFIK_LAT"]) if os.environ.get("TRAFIK_LAT") else None
        lon = float(os.environ["TRAFIK_LON"]) if os.environ.get("TRAFIK_LON") else None
        return cls(
            lat=lat,
            lon=lon,
            state_path=os.environ.get("STATE_PATH", "data/state.json"),
            tomtom_key=need("TOMTOM_API_KEY"),
            telegram_token=need("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=need("TELEGRAM_CHAT_ID"),
            interval=int(os.environ.get("CHECK_INTERVAL_SECONDS", "300")),
            name=os.environ.get("TRAFIK_NAME", ""),
            yogun_esik=float(os.environ.get("YOGUN_ESIK", "0.40")),
            orta_esik=float(os.environ.get("ORTA_ESIK", "0.70")),
            window_start=os.environ.get("NOTIFY_START", ""),
            window_end=os.environ.get("NOTIFY_END", ""),
            days=parse_days(os.environ.get("NOTIFY_DAYS", "")),
            timezone=os.environ.get("TIMEZONE", "Europe/Istanbul"),
        )


def parse_days(v) -> tuple:
    """"0,1,2" veya [0,1,2] -> sıralı tuple; boş = her gün."""
    items = v.split(",") if isinstance(v, str) else v
    days = sorted({int(x) for x in items if str(x).strip() != ""})
    if any(d < 0 or d > 6 for d in days):
        raise ValueError("Gün değerleri 0-6 olmalı")
    return tuple(days) if days else (0, 1, 2, 3, 4, 5, 6)


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


def in_window(cfg: "Config", now: datetime | None = None) -> bool:
    """Şu an bildirim aralığında mı? Gece aşan aralıkta gün, aralığın başladığı güne göre sayılır."""
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(cfg.timezone))
    cur = now.hour * 60 + now.minute
    if not cfg.window_start:
        return now.weekday() in cfg.days
    start, end = _minutes(cfg.window_start), _minutes(cfg.window_end)
    if start < end:
        return start <= cur < end and now.weekday() in cfg.days
    if cur >= start:
        return now.weekday() in cfg.days
    if cur < end:
        return (now - timedelta(days=1)).weekday() in cfg.days
    return False


@dataclass
class Flow:
    current_speed: float
    free_flow_speed: float
    current_time: int
    free_flow_time: int
    road_closure: bool


def fetch_flow(cfg: Config) -> Flow:
    r = requests.get(
        TOMTOM_URL,
        params={"point": f"{cfg.lat},{cfg.lon}", "unit": "KMPH", "key": cfg.tomtom_key},
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


def classify(flow: Flow, cfg: Config) -> str:
    if flow.road_closure:
        return KAPALI
    if flow.free_flow_speed <= 0:
        return AKICI
    ratio = flow.current_speed / flow.free_flow_speed
    if ratio < cfg.yogun_esik:
        return YOGUN
    if ratio < cfg.orta_esik:
        return ORTA
    return AKICI


def format_message(cfg: Config, level: str, flow: Flow) -> str:
    gecikme = max(0, flow.current_time - flow.free_flow_time)
    return (
        f"{EMOJI[level]} {ETIKET[level]} — {cfg.name or f'{cfg.lat:.4f},{cfg.lon:.4f}'}\n"
        f"Hız: {flow.current_speed:.0f} km/s (normalde {flow.free_flow_speed:.0f})\n"
        f"Ek gecikme: ~{gecikme // 60} dk\n"
        f"https://maps.google.com/?q={cfg.lat},{cfg.lon}"
    )


def send_telegram(cfg: Config, text: str) -> None:
    r = requests.post(
        TELEGRAM_URL.format(token=cfg.telegram_token),
        json={"chat_id": cfg.telegram_chat_id, "text": text},
        timeout=15,
    )
    if not r.ok:
        try:
            desc = r.json().get("description", "")
        except ValueError:
            desc = r.text[:100]
        raise RuntimeError(f"Telegram {r.status_code}: {desc}")


class Monitor:
    """Seçili noktayı periyodik kontrol eder; konum çalışırken değiştirilebilir."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.last: dict | None = None
        self._load_state()

    def _load_state(self) -> None:
        try:
            with open(self.cfg.state_path) as f:
                d = json.load(f)
        except (OSError, ValueError):
            return  # kayıtlı durum yok: env değerleri kullanılır
        if "lat" in d and "lon" in d:
            self.cfg.lat, self.cfg.lon, self.cfg.name = d["lat"], d["lon"], d.get("name", "")
        if "window_start" in d:
            self.cfg.window_start, self.cfg.window_end = d["window_start"], d["window_end"]
            self.cfg.days = parse_days(d.get("days", ""))

    def _save_state(self) -> None:  # self.lock altında çağrılır
        c = self.cfg
        os.makedirs(os.path.dirname(c.state_path) or ".", exist_ok=True)
        with open(c.state_path, "w") as f:
            json.dump({"lat": c.lat, "lon": c.lon, "name": c.name, "window_start": c.window_start,
                       "window_end": c.window_end, "days": list(c.days)}, f)

    def set_location(self, lat: float, lon: float, name: str = "") -> None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Geçersiz koordinat")
        with self.lock:
            self.cfg.lat, self.cfg.lon, self.cfg.name = lat, lon, name.strip()[:80]
            self.last = None
            self._save_state()
        self.wake.set()  # hemen yeni noktayı ölç

    def set_schedule(self, start: str, end: str, days) -> None:
        validate_window(start, end)
        days = parse_days(days)
        with self.lock:
            self.cfg.window_start, self.cfg.window_end, self.cfg.days = start, end, days
            self._save_state()
        self.wake.set()

    def status(self) -> dict:
        with self.lock:
            c = self.cfg
            return {
                "lat": c.lat, "lon": c.lon, "name": c.name, "interval": c.interval,
                "last": self.last, "window_start": c.window_start, "window_end": c.window_end,
                "days": list(c.days), "timezone": c.timezone, "active": in_window(c),
            }

    def check_once(self) -> None:
        with self.lock:
            if self.cfg.lat is None:
                return
            cfg = Config(**{**self.cfg.__dict__})
        if not in_window(cfg):
            return  # bildirim saati dışında: ölçüm de yapılmaz (API kotası harcanmaz)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            flow = fetch_flow(cfg)
            level = classify(flow, cfg)
            log.info("%s: %s (%.0f/%.0f km/s)", cfg.name or (cfg.lat, cfg.lon), level,
                     flow.current_speed, flow.free_flow_speed)
            last = {
                "level": level, "label": ETIKET[level], "checked_at": now,
                "current_speed": flow.current_speed, "free_flow_speed": flow.free_flow_speed,
                "delay_s": max(0, flow.current_time - flow.free_flow_time),
            }
            with self.lock:
                if (cfg.lat, cfg.lon) != (self.cfg.lat, self.cfg.lon):
                    return  # ölçüm sırasında konum değişti, sonucu at
                self.last = last
            try:
                send_telegram(cfg, format_message(cfg, level, flow))
            except Exception as e:
                log.error("Telegram gönderilemedi: %s", e)
                with self.lock:
                    self.last = {**last, "notify_error": str(e)[:200]}
        except Exception as e:
            log.exception("Kontrol başarısız, bir sonraki periyotta tekrar denenecek")
            with self.lock:
                self.last = {"error": str(e)[:200], "checked_at": now}

    def run_forever(self) -> None:
        while True:
            self.check_once()
            self.wake.wait(self.cfg.interval)
            self.wake.clear()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    cfg = Config.from_env()
    if cfg.lat is None:
        sys.exit("TRAFIK_LAT / TRAFIK_LON gerekli (web arayüzü için: python web.py)")
    if "--once" in sys.argv:
        flow = fetch_flow(cfg)
        print(format_message(cfg, classify(flow, cfg), flow))
        return
    Monitor(cfg).run_forever()


if __name__ == "__main__":
    main()
