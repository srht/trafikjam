import time

import trafikjam as t
from monitor import Monitor
from store import UserExists

import pytest


def setup_point(store, chat="42", **kw):
    uid = store.create_user("ali", "h")
    store.set_chat_id(uid, chat)
    pid = store.add_point(uid, "Köprü", 41.0, 29.0, kw.get("start", ""), kw.get("end", ""), t.ALL_DAYS)
    return uid, pid


def test_store_isolation_and_duplicates(store):
    a, b = store.create_user("a", "h"), store.create_user("b", "h")
    pid = store.add_point(a, "x", 1, 2, "", "", t.ALL_DAYS)
    assert store.get_point(b, pid) is None
    assert not store.delete_point(b, pid) and not store.update_point(b, pid, "n", "", "", t.ALL_DAYS)
    assert store.get_point(a, pid)
    with pytest.raises(UserExists):
        store.create_user("a", "h")


def test_notifies_every_check_to_owner(settings, store, monkeypatch):
    uid, pid = setup_point(store)
    sent = []
    monkeypatch.setattr(t, "fetch_flow", lambda s, la, lo: t.Flow(90, 100, 60, 60, False))
    monkeypatch.setattr(t, "send_telegram", lambda tok, chat, text: sent.append((tok, chat, text)))
    m = Monitor(settings, store)
    m.tick()
    assert len(sent) == 1 and sent[0][:2] == ("tok", "42")
    m.tick()  # periyot dolmadı
    assert len(sent) == 1
    p = store.get_point(uid, pid)
    assert p["last"]["level"] == t.AKICI and "notify_error" not in p["last"]
    store.mark_checked(pid, time.time() - 400)
    m.tick()
    assert len(sent) == 2


def test_telegram_error_and_missing_chat_surface(settings, store, monkeypatch):
    uid, pid = setup_point(store, chat="")
    monkeypatch.setattr(t, "fetch_flow", lambda s, la, lo: t.Flow(90, 100, 60, 60, False))
    m = Monitor(settings, store)
    m.tick()
    assert "chat id" in store.get_point(uid, pid)["last"]["notify_error"]
    store.set_chat_id(uid, "1")
    store.mark_checked(pid, 0)

    def boom(*a):
        raise RuntimeError("Telegram 400: chat not found")

    monkeypatch.setattr(t, "send_telegram", boom)
    m.tick()
    assert "chat not found" in store.get_point(uid, pid)["last"]["notify_error"]


def test_outside_window_skips_fetch(settings, store, monkeypatch):
    setup_point(store, start="07:00", end="10:00")
    called = []
    monkeypatch.setattr(t, "in_window", lambda *a, **k: False)
    monkeypatch.setattr(t, "fetch_flow", lambda *a: called.append(1))
    Monitor(settings, store).tick()
    assert not called


def test_fetch_error_recorded(settings, store, monkeypatch):
    uid, pid = setup_point(store)

    def boom(*a):
        raise RuntimeError("tomtom down")

    monkeypatch.setattr(t, "fetch_flow", boom)
    Monitor(settings, store).tick()
    assert "tomtom down" in store.get_point(uid, pid)["last"]["error"]
