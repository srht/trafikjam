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
