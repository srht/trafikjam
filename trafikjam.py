"""Belirli bir koordinattaki trafiği periyodik kontrol edip Telegram'dan haber verir."""
import logging
import os
import sys
import time
from dataclasses import dataclass

import requests

TOMTOM_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"

AKICI, ORTA, YOGUN, KAPALI = "akici", "orta", "yogun", "kapali"
EMOJI = {AKICI: "🟢", ORTA: "🟡", YOGUN: "🔴", KAPALI: "⛔"}
ETIKET = {AKICI: "Trafik akıcı", ORTA: "Trafik yoğunlaşıyor", YOGUN: "Trafik sıkışık", KAPALI: "Yol kapalı"}

log = logging.getLogger("trafikjam")


@dataclass
class Config:
    lat: float
    lon: float
    tomtom_key: str
    telegram_token: str
    telegram_chat_id: str
    interval: int = 300
    name: str = ""
    yogun_esik: float = 0.40  # güncel hız / serbest akış hızı bunun altındaysa sıkışık
    orta_esik: float = 0.70

    @classmethod
    def from_env(cls) -> "Config":
        def need(k):
            v = os.environ.get(k)
            if not v:
                sys.exit(f"Eksik ortam değişkeni: {k} (bkz. .env.example)")
            return v

        lat, lon = float(need("TRAFIK_LAT")), float(need("TRAFIK_LON"))
        return cls(
            lat=lat,
            lon=lon,
            tomtom_key=need("TOMTOM_API_KEY"),
            telegram_token=need("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=need("TELEGRAM_CHAT_ID"),
            interval=int(os.environ.get("CHECK_INTERVAL_SECONDS", "300")),
            name=os.environ.get("TRAFIK_NAME", f"{lat},{lon}"),
            yogun_esik=float(os.environ.get("YOGUN_ESIK", "0.40")),
            orta_esik=float(os.environ.get("ORTA_ESIK", "0.70")),
        )


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
        f"{EMOJI[level]} {ETIKET[level]} — {cfg.name}\n"
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
    r.raise_for_status()


def should_notify(prev: str | None, cur: str) -> bool:
    """Sadece durum değişince haber ver; ilk ölçümde yalnızca sorun varsa bildir."""
    if prev is None:
        return cur != AKICI
    return prev != cur


def run(cfg: Config) -> None:
    prev = None
    while True:
        try:
            flow = fetch_flow(cfg)
            level = classify(flow, cfg)
            log.info("%s: %s (%.0f/%.0f km/s)", cfg.name, level, flow.current_speed, flow.free_flow_speed)
            if should_notify(prev, level):
                send_telegram(cfg, format_message(cfg, level, flow))
            prev = level
        except Exception:
            log.exception("Kontrol başarısız, bir sonraki periyotta tekrar denenecek")
        time.sleep(cfg.interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    cfg = Config.from_env()
    if "--once" in sys.argv:
        flow = fetch_flow(cfg)
        print(format_message(cfg, classify(flow, cfg), flow))
        return
    run(cfg)


if __name__ == "__main__":
    main()
