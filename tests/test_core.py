from datetime import datetime, timezone

import pytest

import trafikjam as t


def flow(cur, free=100, closed=False):
    return t.Flow(cur, free, 120, 60, closed)


def test_classify(settings):
    assert t.classify(flow(90), settings) == t.AKICI
    assert t.classify(flow(50), settings) == t.ORTA
    assert t.classify(flow(20), settings) == t.YOGUN
    assert t.classify(flow(90, closed=True), settings) == t.KAPALI


def test_message():
    m = t.format_message("Köprü", 1.0, 2.0, t.YOGUN, flow(20))
    assert "Köprü" in m and "~1 dk" in m and "maps.google.com" in m
    assert "1.0000,2.0000" in t.format_message("", 1.0, 2.0, t.AKICI, flow(90))


def at(h, m=0, day=5):  # 2026-10-05 Pazartesi
    return datetime(2026, 10, day, h, m, tzinfo=timezone.utc)


ALL = t.ALL_DAYS


def test_window_same_day():
    assert t.in_window("07:00", "10:00", ALL, "UTC", at(7)) and t.in_window("07:00", "10:00", ALL, "UTC", at(9, 59))
    assert not t.in_window("07:00", "10:00", ALL, "UTC", at(10))
    assert not t.in_window("07:00", "10:00", ALL, "UTC", at(6, 59))


def test_window_overnight_and_days():
    f = lambda now: t.in_window("22:00", "06:00", (0,), "UTC", now)  # yalnızca Pazartesi başlangıçlı
    assert f(at(23, day=5)) and f(at(3, day=6))
    assert not f(at(3, day=5)) and not f(at(23, day=6))


def test_window_always_and_timezone():
    assert t.in_window("", "", ALL, "UTC", at(3))
    assert not t.in_window("", "", (1,), "UTC", at(3))
    assert t.in_window("07:00", "10:00", ALL, "Europe/Istanbul", at(5))  # 05:00 UTC = 08:00 TR


def test_validation():
    t.validate_window("", "")
    t.validate_window("07:00", "10:00")
    for bad in [("07:00", ""), ("7", "10:00"), ("25:00", "10:00"), ("08:00", "08:00")]:
        with pytest.raises(ValueError):
            t.validate_window(*bad)
    with pytest.raises(ValueError):
        t.parse_days([7])
    assert t.parse_days([]) == t.ALL_DAYS


def test_secret_persists(tmp_path):
    a = t._persistent_secret(str(tmp_path))
    assert a == t._persistent_secret(str(tmp_path)) and len(a) == 64
