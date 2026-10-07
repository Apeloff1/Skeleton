"""High-integrity append-only event journal for long-running companion sessions."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
import sqlite3
from typing import Any, Mapping

SCHEMA = "skeleton.ai.dragon_crawl.event.v1"
ALLOWED = frozenset(("frontier_discovered","dragon_travel","visual_probe","robots_check","fetch_started","fetch_received","policy_rejected","acquisition_accepted","burn_started","burn_chunk","burn_complete","retry_wait","crawl_complete"))

def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

@dataclass(frozen=True)
class StoredDragonEvent:
    session_id: str
    sequence: int
    event_id: str
    kind: str
    url: str
    at: float
    payload: dict[str, Any]
    previous_digest: str
    digest: str

    def wire(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "sequence": self.sequence, "event_id": self.event_id,
                "kind": self.kind, "url": self.url, "at": self.at, "payload": self.payload}

class DragonEventJournal:
    """Transactional SQLite journal; digest chain detects accidental tampering.

    Authentication and access control must be enforced by the API serving this journal.
    A hash chain is not a digital signature or proof of source authenticity.
    """
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_companion_events (
          session_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_id TEXT NOT NULL,
          kind TEXT NOT NULL, url TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL,
          previous_digest TEXT NOT NULL, digest TEXT NOT NULL,
          PRIMARY KEY(session_id, sequence), UNIQUE(session_id, event_id))""")
        self.db.commit()

    def append(self, session_id: str, kind: str, url: str, *, at: float,
               payload: Mapping[str, Any] | None = None) -> StoredDragonEvent:
        if not session_id or len(session_id) > 128 or kind not in ALLOWED:
            raise ValueError("invalid session or event kind")
        if not url.startswith(("https://", "http://")) or len(url) > 4096:
            raise ValueError("invalid event URL")
        if not math.isfinite(at):
            raise ValueError("event time must be finite")
        data = dict(payload or {})
        encoded = _canonical(data)
        if len(encoded.encode("utf-8")) > 32768:
            raise ValueError("event payload exceeds limit")
        with self.db:
            row = self.db.execute(
                "SELECT sequence,digest FROM dragon_companion_events WHERE session_id=? ORDER BY sequence DESC LIMIT 1",
                (session_id,)).fetchone()
            sequence = row[0] + 1 if row else 1
            previous = row[1] if row else "0" * 64
            base = {"session_id": session_id, "sequence": sequence, "kind": kind,
                    "url": url, "at": at, "payload": data, "previous_digest": previous}
            digest = hashlib.sha256(_canonical(base).encode("utf-8")).hexdigest()
            event_id = digest
            self.db.execute(
                "INSERT INTO dragon_companion_events VALUES(?,?,?,?,?,?,?,?,?)",
                (session_id, sequence, event_id, kind, url, at, encoded, previous, digest))
        return StoredDragonEvent(session_id, sequence, event_id, kind, url, at, data, previous, digest)

    def page(self, session_id: str, *, after: int = 0, limit: int = 100) -> dict[str, Any]:
        if not session_id or after < 0 or not 1 <= limit <= 1000:
            raise ValueError("invalid page parameters")
        rows = self.db.execute(
            "SELECT sequence,event_id,kind,url,at,payload,previous_digest,digest "
            "FROM dragon_companion_events WHERE session_id=? AND sequence>? "
            "ORDER BY sequence LIMIT ?", (session_id, after, limit + 1)).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        events = [StoredDragonEvent(session_id, r[0], r[1], r[2], r[3], r[4],
                                    json.loads(r[5]), r[6], r[7]).wire() for r in rows]
        return {"events": events, "nextCursor": str(rows[-1][0]) if rows else None,
                "hasMore": has_more}

    def verify(self, session_id: str) -> bool:
        previous = "0" * 64
        rows = self.db.execute(
            "SELECT sequence,event_id,kind,url,at,payload,previous_digest,digest "
            "FROM dragon_companion_events WHERE session_id=? ORDER BY sequence",
            (session_id,)).fetchall()
        for index, r in enumerate(rows, 1):
            seq, event_id, kind, url, at, payload, parent, digest = r
            if seq != index or parent != previous or event_id != digest:
                return False
            base = {"session_id": session_id, "sequence": seq, "kind": kind,
                    "url": url, "at": at, "payload": json.loads(payload),
                    "previous_digest": parent}
            if hashlib.sha256(_canonical(base).encode("utf-8")).hexdigest() != digest:
                return False
            previous = digest
        return True
