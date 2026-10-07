import threading

import pytest

import trafikjam as t
import web
from store import Store


class StubMonitor:
    def __init__(self):
        self.wake = threading.Event()


@pytest.fixture
def settings(tmp_path):
    return t.Settings(tomtom_key="k", telegram_token="tok", data_dir=str(tmp_path), cookie_secure=False,
                      timezone="UTC", max_points=2)


@pytest.fixture
def store(settings):
    return Store(settings.db_path)


@pytest.fixture
def app(settings, store):
    return web.create_app(settings, store, StubMonitor())


H = {"X-Requested-With": "fetch"}


def new_client(app, username="ali", password="sifre1234"):
    c = app.test_client()
    r = c.post("/api/register", json={"username": username, "password": password}, headers=H)
    assert r.status_code == 201, r.json
    return c
