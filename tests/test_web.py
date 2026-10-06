import base64

import trafikjam as t
import web


def make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "ADMIN_PASSWORD", "pw")
    cfg = t.Config(lat=None, lon=None, tomtom_key="k", telegram_token="x",
                   telegram_chat_id="1", state_path=str(tmp_path / "s.json"))
    web.monitor = t.Monitor(cfg)
    return web.app.test_client()


AUTH = {"Authorization": "Basic " + base64.b64encode(b"u:pw").decode()}


def test_requires_auth(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    assert c.get("/api/status").status_code == 401
    assert c.post("/api/location", json={"lat": 1, "lon": 2}).status_code == 401


def test_set_and_get_location(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    r = c.post("/api/location", json={"lat": 41.0, "lon": 29.0, "name": "x"}, headers=AUTH)
    assert r.status_code == 200
    assert c.get("/api/status", headers=AUTH).json["lat"] == 41.0
    assert c.post("/api/location", json={"lat": 200, "lon": 0}, headers=AUTH).status_code == 400
    assert c.post("/api/location", json={}, headers=AUTH).status_code == 400
    assert c.get("/", headers=AUTH).status_code == 200
