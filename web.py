"""Web arayüzü + API: kayıt/giriş, kullanıcıya özel noktalar, arka plan izleyici."""
import hmac
import logging
import os
import re
import threading
import time
from datetime import timedelta
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import trafikjam as t
from monitor import Monitor
from store import Store, UserExists

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
CHAT_ID_RE = re.compile(r"^-?\d{1,20}$")
DUMMY_HASH = generate_password_hash("dummy-password")  # kullanıcı yokken de aynı sürede yanıt vermek için


class Throttle:
    """Bellek içi basit sınırlayıcı: pencere içinde `limit` başarısızlıktan sonra bloklar."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self.hits: dict = {}
        self.lock = threading.Lock()

    def _prune(self, key):
        cutoff = time.time() - self.window
        self.hits[key] = [x for x in self.hits.get(key, []) if x > cutoff]
        if not self.hits[key]:
            del self.hits[key]

    def blocked(self, key) -> bool:
        with self.lock:
            self._prune(key)
            return len(self.hits.get(key, [])) >= self.limit

    def hit(self, key) -> None:
        with self.lock:
            self.hits.setdefault(key, []).append(time.time())

    def reset(self, key) -> None:
        with self.lock:
            self.hits.pop(key, None)


def create_app(settings: t.Settings, store: Store, monitor) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.secret_key = settings.secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.cookie_secure,
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # Dokploy/Traefik arkasında
    login_throttle = Throttle(limit=5, window=900)
    register_throttle = Throttle(limit=10, window=3600)

    def err(msg, code=400):
        return jsonify(error=msg), code

    @app.before_request
    def csrf_guard():
        # Çapraz site formları özel başlık gönderemez; SameSite=Lax çerezle birlikte CSRF'i engeller.
        if request.path.startswith("/api/") and request.method not in ("GET", "HEAD"):
            if request.headers.get("X-Requested-With") != "fetch":
                return err("Geçersiz istek", 403)

    def login_required(f):
        @wraps(f)
        def wrapper(*a, **kw):
            user = store.get_user(session["uid"]) if "uid" in session else None
            if not user:
                session.clear()
                return err("Giriş gerekli", 401)
            return f(user, *a, **kw)
        return wrapper

    def point_json(p):
        return {
            "id": p["id"], "name": p["name"], "lat": p["lat"], "lon": p["lon"],
            "window_start": p["window_start"], "window_end": p["window_end"], "days": p["days"],
            "last": p["last"],
            "active": t.in_window(p["window_start"], p["window_end"], tuple(p["days"]), settings.timezone),
        }

    def parse_schedule(d):
        start, end = str(d.get("start", "")), str(d.get("end", ""))
        t.validate_window(start, end)
        days = d.get("days", [])
        if not isinstance(days, list):
            raise ValueError("days liste olmalı")
        return start, end, t.parse_days(days)

    def clean_name(d):
        return str(d.get("name", "")).strip()[:80]

    # --- sayfa ---
    @app.get("/")
    def index():
        return send_from_directory("static", "index.html")

    @app.get("/api/config")
    def config():
        return jsonify(registration_code_required=bool(settings.registration_code),
                       interval=settings.interval, timezone=settings.timezone,
                       max_points=settings.max_points)

    # --- hesap ---
    @app.post("/api/register")
    def register():
        d = request.get_json(silent=True) or {}
        ip = request.remote_addr
        if register_throttle.blocked(ip):
            return err("Çok fazla deneme, daha sonra tekrar dene", 429)
        register_throttle.hit(ip)
        if settings.registration_code and not hmac.compare_digest(
                str(d.get("code", "")).encode(), settings.registration_code.encode()):
            return err("Davet kodu yanlış", 403)
        username, password = str(d.get("username", "")).strip(), str(d.get("password", ""))
        if not USERNAME_RE.match(username):
            return err("Kullanıcı adı 3-32 karakter olmalı (harf, rakam, _ . -)")
        if not 8 <= len(password) <= 128:
            return err("Şifre 8-128 karakter olmalı")
        try:
            uid = store.create_user(username.lower(), generate_password_hash(password))
        except UserExists:
            return err("Bu kullanıcı adı alınmış", 409)
        session.clear()
        session["uid"] = uid
        session.permanent = True
        return jsonify(username=username.lower()), 201

    @app.post("/api/login")
    def login():
        d = request.get_json(silent=True) or {}
        username, password = str(d.get("username", "")).strip().lower(), str(d.get("password", ""))
        key = (username, request.remote_addr)
        if login_throttle.blocked(key):
            return err("Çok fazla hatalı deneme, 15 dakika sonra tekrar dene", 429)
        user = store.get_user_by_name(username)
        ok = check_password_hash(user["password_hash"] if user else DUMMY_HASH, password)
        if not (user and ok):
            login_throttle.hit(key)
            return err("Kullanıcı adı veya şifre hatalı", 401)
        login_throttle.reset(key)
        session.clear()
        session["uid"] = user["id"]
        session.permanent = True
        return jsonify(username=user["username"])

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    @login_required
    def me(user):
        return jsonify(username=user["username"], chat_id=user["chat_id"])

    @app.post("/api/telegram")
    @login_required
    def set_telegram(user):
        chat_id = str((request.get_json(silent=True) or {}).get("chat_id", "")).strip()
        if chat_id and not CHAT_ID_RE.match(chat_id):
            return err("Chat id sayı olmalı (grup ise başında - olabilir)")
        store.set_chat_id(user["id"], chat_id)
        return jsonify(chat_id=chat_id)

    @app.post("/api/telegram/test")
    @login_required
    def test_telegram(user):
        if not user["chat_id"]:
            return err("Önce chat id gir ve kaydet")
        try:
            t.send_telegram(settings.telegram_token, user["chat_id"], "✅ Trafik Jam: test mesajı, bildirimler çalışıyor.")
        except Exception as e:
            return err(str(e)[:200], 502)
        return jsonify(ok=True)

    # --- noktalar ---
    @app.get("/api/points")
    @login_required
    def list_points(user):
        return jsonify(points=[point_json(p) for p in store.list_points(user["id"])])

    @app.post("/api/points")
    @login_required
    def add_point(user):
        d = request.get_json(silent=True) or {}
        try:
            lat, lon = float(d["lat"]), float(d["lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            return err("Geçersiz koordinat")
        try:
            start, end, days = parse_schedule(d)
        except ValueError as e:
            return err(str(e))
        if store.count_points(user["id"]) >= settings.max_points:
            return err(f"En fazla {settings.max_points} nokta ekleyebilirsin", 409)
        pid = store.add_point(user["id"], clean_name(d), lat, lon, start, end, days)
        monitor.wake.set()
        return jsonify(point_json(store.get_point(user["id"], pid))), 201

    @app.patch("/api/points/<int:pid>")
    @login_required
    def update_point(user, pid):
        d = request.get_json(silent=True) or {}
        try:
            start, end, days = parse_schedule(d)
        except ValueError as e:
            return err(str(e))
        if not store.update_point(user["id"], pid, clean_name(d), start, end, days):
            return err("Nokta bulunamadı", 404)
        monitor.wake.set()
        return jsonify(point_json(store.get_point(user["id"], pid)))

    @app.delete("/api/points/<int:pid>")
    @login_required
    def delete_point(user, pid):
        if not store.delete_point(user["id"], pid):
            return err("Nokta bulunamadı", 404)
        return jsonify(ok=True)

    return app


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    settings = t.Settings.from_env()
    store = Store(settings.db_path)
    monitor = Monitor(settings, store)
    threading.Thread(target=monitor.run_forever, daemon=True).start()
    from waitress import serve

    serve(create_app(settings, store, monitor), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
