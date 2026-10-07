"""Arka plan izleyici: tüm kullanıcıların noktalarını periyodik ölçer, sahibine Telegram'dan bildirir."""
import logging
import threading
import time
from datetime import datetime, timezone

import trafikjam as t
from store import Store

log = logging.getLogger("trafikjam")
TICK_SECONDS = 15


class Monitor:
    def __init__(self, settings: t.Settings, store: Store):
        self.s = settings
        self.store = store
        self.wake = threading.Event()

    def check_point(self, p: dict) -> None:
        now = time.time()
        self.store.mark_checked(p["id"], now)  # hata olsa bile bir sonraki periyoda kadar tekrar denenmez
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            flow = t.fetch_flow(self.s, p["lat"], p["lon"])
        except Exception as e:
            log.exception("Ölçüm başarısız (nokta %s)", p["id"])
            self.store.save_result(p["id"], {"error": str(e)[:200], "checked_at": stamp})
            return
        level = t.classify(flow, self.s)
        last = {
            "level": level, "label": t.ETIKET[level], "checked_at": stamp,
            "current_speed": flow.current_speed, "free_flow_speed": flow.free_flow_speed,
            "delay_s": max(0, flow.current_time - flow.free_flow_time),
        }
        log.info("nokta %s: %s (%.0f/%.0f km/s)", p["id"], level, flow.current_speed, flow.free_flow_speed)
        if not p["chat_id"]:
            last["notify_error"] = "Telegram chat id girilmemiş"
        else:
            try:
                t.send_telegram(self.s.telegram_token, p["chat_id"],
                                t.format_message(p["name"], p["lat"], p["lon"], level, flow))
            except Exception as e:
                log.error("Telegram gönderilemedi (nokta %s): %s", p["id"], e)
                last["notify_error"] = str(e)[:200]
        self.store.save_result(p["id"], last)

    def tick(self) -> None:
        for p in self.store.due_points(time.time() - self.s.interval):
            if t.in_window(p["window_start"], p["window_end"], tuple(p["days"]), self.s.timezone):
                self.check_point(p)

    def run_forever(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:
                log.exception("Tick başarısız")
            self.wake.wait(TICK_SECONDS)
            self.wake.clear()
