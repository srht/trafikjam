import trafikjam as t

CFG = t.Config(lat=1, lon=2, tomtom_key="k", telegram_token="x", telegram_chat_id="1")


def flow(cur, free=100, closed=False):
    return t.Flow(cur, free, 120, 60, closed)


def test_classify():
    assert t.classify(flow(90), CFG) == t.AKICI
    assert t.classify(flow(50), CFG) == t.ORTA
    assert t.classify(flow(20), CFG) == t.YOGUN
    assert t.classify(flow(90, closed=True), CFG) == t.KAPALI


def test_message_has_delay():
    assert "~1 dk" in t.format_message(CFG, t.YOGUN, flow(20))


def test_set_location_persists(tmp_path):
    cfg = t.Config(lat=None, lon=None, tomtom_key="k", telegram_token="x",
                   telegram_chat_id="1", state_path=str(tmp_path / "s.json"))
    m = t.Monitor(cfg)
    m.set_location(41.0, 29.0, "Köprü")
    cfg2 = t.Config(lat=None, lon=None, tomtom_key="k", telegram_token="x",
                    telegram_chat_id="1", state_path=str(tmp_path / "s.json"))
    t.Monitor(cfg2)
    assert (cfg2.lat, cfg2.lon, cfg2.name) == (41.0, 29.0, "Köprü")


def test_set_location_rejects_invalid(tmp_path):
    import pytest
    m = t.Monitor(t.Config(lat=None, lon=None, tomtom_key="k", telegram_token="x",
                           telegram_chat_id="1", state_path=str(tmp_path / "s.json")))
    with pytest.raises(ValueError):
        m.set_location(91, 0)


def test_notifies_every_check_and_surfaces_telegram_error(tmp_path, monkeypatch):
    cfg = t.Config(lat=1, lon=2, tomtom_key="k", telegram_token="x",
                   telegram_chat_id="1", state_path=str(tmp_path / "s.json"))
    m = t.Monitor(cfg)
    monkeypatch.setattr(t, "fetch_flow", lambda c: flow(90))
    sent = []
    monkeypatch.setattr(t, "send_telegram", lambda c, text: sent.append(text))
    m.check_once()
    m.check_once()
    assert len(sent) == 2 and "notify_error" not in m.last

    def boom(c, text):
        raise RuntimeError("Telegram 400: chat not found")

    monkeypatch.setattr(t, "send_telegram", boom)
    m.check_once()
    assert "chat not found" in m.last["notify_error"]


def _cfg(tmp_path, **kw):
    return t.Config(lat=1, lon=2, tomtom_key="k", telegram_token="x", telegram_chat_id="1",
                    state_path=str(tmp_path / "s.json"), timezone="UTC", **kw)


def _at(h, m=0, day=5):  # 2026-10-05 Pazartesi
    from datetime import datetime, timezone
    return datetime(2026, 10, day, h, m, tzinfo=timezone.utc)


def test_in_window_same_day(tmp_path):
    c = _cfg(tmp_path, window_start="07:00", window_end="10:00")
    assert t.in_window(c, _at(7)) and t.in_window(c, _at(9, 59))
    assert not t.in_window(c, _at(10)) and not t.in_window(c, _at(6, 59))


def test_in_window_overnight_and_days(tmp_path):
    c = _cfg(tmp_path, window_start="22:00", window_end="06:00", days=(0,))  # sadece Pazartesi başlangıçlı
    assert t.in_window(c, _at(23, day=5))        # Pzt 23:00
    assert t.in_window(c, _at(3, day=6))         # Salı 03:00 (Pzt gecesinin devamı)
    assert not t.in_window(c, _at(3, day=5))     # Pzt 03:00 (Pazar gecesi)
    assert not t.in_window(c, _at(23, day=6))    # Salı 23:00


def test_always_when_no_window(tmp_path):
    assert t.in_window(_cfg(tmp_path), _at(3))
    assert not t.in_window(_cfg(tmp_path, days=(1,)), _at(3))


def test_outside_window_skips_fetch_and_persists(tmp_path, monkeypatch):
    import pytest
    m = t.Monitor(_cfg(tmp_path))
    m.set_schedule("07:00", "10:00", [0, 1])
    m2 = t.Monitor(_cfg(tmp_path))
    assert (m2.cfg.window_start, m2.cfg.window_end, m2.cfg.days) == ("07:00", "10:00", (0, 1))
    called = []
    monkeypatch.setattr(t, "in_window", lambda c, now=None: False)
    monkeypatch.setattr(t, "fetch_flow", lambda c: called.append(1))
    m.check_once()
    assert not called
    for bad in [("07:00", ""), ("7", "10:00"), ("25:00", "10:00"), ("08:00", "08:00")]:
        with pytest.raises(ValueError):
            m.set_schedule(*bad, [])
    with pytest.raises(ValueError):
        m.set_schedule("", "", [7])
