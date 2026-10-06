import trafikjam as t

CFG = t.Config(lat=1, lon=2, tomtom_key="k", telegram_token="x", telegram_chat_id="1")


def flow(cur, free=100, closed=False):
    return t.Flow(cur, free, 120, 60, closed)


def test_classify():
    assert t.classify(flow(90), CFG) == t.AKICI
    assert t.classify(flow(50), CFG) == t.ORTA
    assert t.classify(flow(20), CFG) == t.YOGUN
    assert t.classify(flow(90, closed=True), CFG) == t.KAPALI


def test_should_notify():
    assert not t.should_notify(None, t.AKICI)
    assert t.should_notify(None, t.YOGUN)
    assert not t.should_notify(t.YOGUN, t.YOGUN)
    assert t.should_notify(t.YOGUN, t.AKICI)


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
