"""SQLite depolama: kullanıcılar ve onların izlediği noktalar."""
import json
import os
import sqlite3
from contextlib import contextmanager

from trafikjam import ALL_DAYS

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    chat_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS points (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    window_start TEXT NOT NULL DEFAULT '',
    window_end TEXT NOT NULL DEFAULT '',
    days TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
    last TEXT,
    last_checked REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS points_user ON points(user_id);
"""


class UserExists(Exception):
    pass


def _point(row) -> dict:
    d = dict(row)
    d["days"] = [int(x) for x in d["days"].split(",")] if d["days"] else list(ALL_DAYS)
    d["last"] = json.loads(d["last"]) if d["last"] else None
    return d


class Store:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)
            db.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    # kullanıcılar
    def create_user(self, username: str, password_hash: str) -> int:
        try:
            with self._db() as db:
                return db.execute("INSERT INTO users(username, password_hash) VALUES (?, ?)",
                                  (username, password_hash)).lastrowid
        except sqlite3.IntegrityError:
            raise UserExists(username) from None

    def get_user_by_name(self, username: str) -> dict | None:
        with self._db() as db:
            r = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(r) if r else None

    def get_user(self, uid: int) -> dict | None:
        with self._db() as db:
            r = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        return dict(r) if r else None

    def set_chat_id(self, uid: int, chat_id: str) -> None:
        with self._db() as db:
            db.execute("UPDATE users SET chat_id = ? WHERE id = ?", (chat_id, uid))

    # noktalar (her sorgu user_id ile sınırlı: başkasının noktasına erişilemez)
    def count_points(self, uid: int) -> int:
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM points WHERE user_id = ?", (uid,)).fetchone()[0]

    def add_point(self, uid: int, name: str, lat: float, lon: float, start: str, end: str, days) -> int:
        with self._db() as db:
            return db.execute(
                "INSERT INTO points(user_id, name, lat, lon, window_start, window_end, days) VALUES (?,?,?,?,?,?,?)",
                (uid, name, lat, lon, start, end, ",".join(map(str, days)))).lastrowid

    def list_points(self, uid: int) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM points WHERE user_id = ? ORDER BY id", (uid,)).fetchall()
        return [_point(r) for r in rows]

    def get_point(self, uid: int, pid: int) -> dict | None:
        with self._db() as db:
            r = db.execute("SELECT * FROM points WHERE id = ? AND user_id = ?", (pid, uid)).fetchone()
        return _point(r) if r else None

    def update_point(self, uid: int, pid: int, name: str, start: str, end: str, days) -> bool:
        with self._db() as db:
            # last_checked=0: ayar değişince hemen yeniden ölçülsün
            n = db.execute(
                "UPDATE points SET name=?, window_start=?, window_end=?, days=?, last_checked=0 "
                "WHERE id=? AND user_id=?", (name, start, end, ",".join(map(str, days)), pid, uid)).rowcount
        return n > 0

    def delete_point(self, uid: int, pid: int) -> bool:
        with self._db() as db:
            return db.execute("DELETE FROM points WHERE id=? AND user_id=?", (pid, uid)).rowcount > 0

    # izleyici
    def due_points(self, checked_before: float) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT p.*, u.chat_id FROM points p JOIN users u ON u.id = p.user_id "
                "WHERE p.last_checked <= ?", (checked_before,)).fetchall()
        return [_point(r) for r in rows]

    def mark_checked(self, pid: int, ts: float) -> None:
        with self._db() as db:
            db.execute("UPDATE points SET last_checked = ? WHERE id = ?", (ts, pid))

    def save_result(self, pid: int, last: dict) -> None:
        with self._db() as db:
            db.execute("UPDATE points SET last = ? WHERE id = ?", (json.dumps(last), pid))
