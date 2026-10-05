from __future__ import annotations
"""
Marathon persistence — encrypted-ready, twin-aware, multi-surface store.
Priority #1 page marathon: real local persistence beyond jsonl tails.
"""

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from gameforge.persistence.encrypt_pages import PageCipher


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class MarathonStore:
    """
    SQLite-backed surface store per user.
    Tables: kv, events, room_logs, features, lessons
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        root = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.dir = root / "marathon" / user_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "marathon.sqlite3"
        self._lock = threading.RLock()
        self.cipher = PageCipher()
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._lock, self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv (
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    surface TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_surface ON events(surface);
                CREATE TABLE IF NOT EXISTS room_logs (
                    id TEXT PRIMARY KEY,
                    room_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload TEXT,
                    raw_text TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_room_logs_room ON room_logs(room_id);
                CREATE TABLE IF NOT EXISTS features (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    score REAL,
                    status TEXT,
                    payload TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    kind TEXT,
                    pattern TEXT,
                    action TEXT,
                    weight REAL,
                    payload TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def kv_set(self, key: str, value: Any) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO kv(k,v,updated_at) VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at",
                (key, json.dumps(value, default=str), _ts()),
            )

    def kv_get(self, key: str, default=None) -> Any:
        with self._lock, self._conn() as c:
            row = c.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
            if not row:
                return default
            return json.loads(row["v"])

    def event(self, surface: str, event: str, payload: Optional[dict] = None) -> str:
        eid = str(uuid.uuid4())[:12]
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO events(id,surface,event,payload,created_at) VALUES(?,?,?,?,?)",
                (eid, surface, event, json.dumps(payload or {}, default=str), _ts()),
            )
        return eid

    def room_log(self, room_id: str, event: str, payload: Optional[dict] = None, raw_text: str = "") -> str:
        eid = str(uuid.uuid4())[:12]
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO room_logs(id,room_id,event,payload,raw_text,created_at) VALUES(?,?,?,?,?,?)",
                (eid, room_id, event, json.dumps(payload or {}, default=str), raw_text, _ts()),
            )
        return eid

    def room_tail(self, room_id: str, n: int = 50) -> List[Dict[str, Any]]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM room_logs WHERE room_id=? ORDER BY created_at DESC LIMIT ?",
                (room_id, n),
            ).fetchall()
        out = []
        for r in reversed(rows):
            out.append(
                {
                    "id": r["id"],
                    "room_id": r["room_id"],
                    "event": r["event"],
                    "payload": json.loads(r["payload"] or "{}"),
                    "raw_text": r["raw_text"],
                    "created_at": r["created_at"],
                }
            )
        return out

    def upsert_feature(self, feature_id: str, name: str, score: float, status: str, payload: Optional[dict] = None):
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO features(id,name,score,status,payload,updated_at) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, score=excluded.score, status=excluded.status,
                   payload=excluded.payload, updated_at=excluded.updated_at""",
                (feature_id, name, score, status, json.dumps(payload or {}, default=str), _ts()),
            )

    def add_lesson(self, lesson_id: str, kind: str, pattern: str, action: str, weight: float, payload: Optional[dict] = None):
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO lessons(id,kind,pattern,action,weight,payload,created_at) VALUES(?,?,?,?,?,?,?)",
                (lesson_id, kind, pattern, action, weight, json.dumps(payload or {}, default=str), _ts()),
            )

    def stats(self) -> Dict[str, Any]:
        with self._lock, self._conn() as c:
            def count(table: str) -> int:
                return c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            return {
                "user_id": self.user_id,
                "db": str(self.db_path),
                "kv": count("kv"),
                "events": count("events"),
                "room_logs": count("room_logs"),
                "features": count("features"),
                "lessons": count("lessons"),
            }

    def kv_set_secure(self, key: str, value: Any) -> None:
        token = self.cipher.encrypt_b64(json.dumps(value, default=str))
        self.kv_set(key, {"_enc": token})

    def kv_get_secure(self, key: str, default=None) -> Any:
        raw = self.kv_get(key, None)
        if not isinstance(raw, dict) or "_enc" not in raw:
            return default if raw is None else raw
        try:
            return json.loads(self.cipher.decrypt_b64(raw["_enc"]))
        except Exception:
            return default
