"""Haritadan konum seçilen web arayüzü + arka plan trafik izleyici."""
import hmac
import logging
import os
import sys
import threading

from flask import Flask, Response, jsonify, request, send_from_directory

from trafikjam import Config, Monitor

app = Flask(__name__, static_folder="static", static_url_path="/static")
monitor: Monitor | None = None
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


@app.before_request
def require_auth():
    a = request.authorization
    ok = a and hmac.compare_digest((a.password or "").encode(), ADMIN_PASSWORD.encode())
    if not ok:
        return Response("Giriş gerekli", 401, {"WWW-Authenticate": 'Basic realm="trafikjam"'})


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/status")
def status():
    return jsonify(monitor.status())


@app.post("/api/location")
def set_location():
    d = request.get_json(silent=True) or {}
    try:
        monitor.set_location(float(d["lat"]), float(d["lon"]), str(d.get("name", "")))
    except (KeyError, TypeError, ValueError) as e:
        return jsonify(error=str(e) or "Geçersiz istek"), 400
    return jsonify(monitor.status())


def create_monitor() -> Monitor:
    global monitor
    monitor = Monitor(Config.from_env())
    threading.Thread(target=monitor.run_forever, daemon=True).start()
    return monitor


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    global ADMIN_PASSWORD
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    if not ADMIN_PASSWORD:
        sys.exit("ADMIN_PASSWORD gerekli (arayüze erişimi korur)")
    create_monitor()
    from waitress import serve

    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
