import web
from conftest import H, StubMonitor, new_client


def test_register_login_logout(app):
    c = new_client(app, "Ali")
    assert c.get("/api/me").json["username"] == "ali"
    c.post("/api/logout", headers=H)
    assert c.get("/api/me").status_code == 401
    assert c.post("/api/login", json={"username": "ALI", "password": "sifre1234"}, headers=H).status_code == 200
    assert c.get("/api/me").status_code == 200


def test_register_validation(app):
    c = app.test_client()
    post = lambda **d: c.post("/api/register", json=d, headers=H)
    assert post(username="ab", password="sifre1234").status_code == 400
    assert post(username="a b!", password="sifre1234").status_code == 400
    assert post(username="ali", password="kisa").status_code == 400
    assert post(username="ali", password="sifre1234").status_code == 201
    assert post(username="ALI", password="sifre1234").status_code == 409


def test_registration_code(settings, store):
    settings.registration_code = "davet"
    c = web.create_app(settings, store, StubMonitor()).test_client()
    assert c.post("/api/register", json={"username": "ali", "password": "sifre1234"}, headers=H).status_code == 403
    r = c.post("/api/register", json={"username": "ali", "password": "sifre1234", "code": "davet"}, headers=H)
    assert r.status_code == 201


def test_login_throttle(app):
    new_client(app)
    c = app.test_client()
    for _ in range(5):
        assert c.post("/api/login", json={"username": "ali", "password": "yanlis"}, headers=H).status_code == 401
    assert c.post("/api/login", json={"username": "ali", "password": "sifre1234"}, headers=H).status_code == 429


def test_unknown_user_login(app):
    r = app.test_client().post("/api/login", json={"username": "yok", "password": "x"}, headers=H)
    assert r.status_code == 401 and "hatalı" in r.json["error"]


def test_csrf_header_required(app):
    c = new_client(app)
    assert c.post("/api/points", json={"lat": 1, "lon": 2}).status_code == 403
    assert c.post("/api/logout").status_code == 403


def test_auth_required(app):
    c = app.test_client()
    assert c.get("/api/points").status_code == 401
    assert c.post("/api/points", json={"lat": 1, "lon": 2}, headers=H).status_code == 401
    assert c.get("/").status_code == 200  # sayfa herkese açık, veri değil


def test_points_crud_and_isolation(app):
    a, b = new_client(app, "ali"), new_client(app, "veli")
    r = a.post("/api/points", json={"lat": 41, "lon": 29, "name": "<b>x</b>", "start": "07:00", "end": "10:00",
                                    "days": [0, 1]}, headers=H)
    assert r.status_code == 201
    pid = r.json["id"]
    assert [p["id"] for p in a.get("/api/points").json["points"]] == [pid]
    assert b.get("/api/points").json["points"] == []
    assert b.patch(f"/api/points/{pid}", json={"name": "hack"}, headers=H).status_code == 404
    assert b.delete(f"/api/points/{pid}", headers=H).status_code == 404
    r = a.patch(f"/api/points/{pid}", json={"name": "y", "start": "", "end": "", "days": []}, headers=H)
    assert r.status_code == 200 and r.json["window_start"] == "" and r.json["days"] == [0, 1, 2, 3, 4, 5, 6]
    assert a.delete(f"/api/points/{pid}", headers=H).status_code == 200
    assert a.get("/api/points").json["points"] == []


def test_point_validation_and_limit(app):
    c = new_client(app)
    bad = [{"lat": 200, "lon": 0}, {"lat": "x", "lon": 0}, {}, {"lat": 1, "lon": 2, "start": "07:00"},
           {"lat": 1, "lon": 2, "days": "abc"}, {"lat": 1, "lon": 2, "days": [9]}]
    for d in bad:
        assert c.post("/api/points", json=d, headers=H).status_code == 400, d
    for _ in range(2):  # max_points=2
        assert c.post("/api/points", json={"lat": 1, "lon": 2}, headers=H).status_code == 201
    assert c.post("/api/points", json={"lat": 1, "lon": 2}, headers=H).status_code == 409


def test_telegram_endpoints(app, monkeypatch):
    c = new_client(app)
    assert c.post("/api/telegram", json={"chat_id": "abc"}, headers=H).status_code == 400
    assert c.post("/api/telegram/test", headers=H).status_code == 400  # chat id yok
    assert c.post("/api/telegram", json={"chat_id": "-100123"}, headers=H).status_code == 200
    assert c.get("/api/me").json["chat_id"] == "-100123"
    sent = []
    monkeypatch.setattr(web.t, "send_telegram", lambda tok, chat, text: sent.append((tok, chat)))
    assert c.post("/api/telegram/test", headers=H).status_code == 200 and sent == [("tok", "-100123")]

    def boom(*a):
        raise RuntimeError("Telegram 400: chat not found")

    monkeypatch.setattr(web.t, "send_telegram", boom)
    r = c.post("/api/telegram/test", headers=H)
    assert r.status_code == 502 and "chat not found" in r.json["error"]
