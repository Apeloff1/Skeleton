"""High-integrity append-only event journal for long-running companion sessions."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
import re
import sqlite3
from urllib.parse import urlsplit
from typing import Any, Mapping

SCHEMA = "skeleton.ai.dragon_crawl.event.v1"
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def _validate_source_url(url: object) -> str:
    """Bound the journal's asserted HTTP origin; this does not grant fetch rights."""
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 32 for c in url):
        raise ValueError("invalid event URL")
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment):
            raise ValueError("invalid event URL")
        _ = parsed.port
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid event URL") from exc
    return url
ALLOWED = frozenset(("frontier_discovered","dragon_travel","visual_probe","robots_check","fetch_started","fetch_received","policy_rejected","acquisition_accepted","burn_started","burn_chunk","burn_complete","retry_wait","crawl_complete"))


def _bounded_json_tree(value: Mapping[str, Any]) -> None:
    """Admit finite canonical JSON before serialization allocates large strings.

    Caps depth and entries, including for malicious Mapping subclasses and
    deeply nested arrays whose encoded result might otherwise exhaust memory.
    """
    stack = [(value, 0)]
    visited = 0
    while stack:
        current, depth = stack.pop()
        visited += 1
        if visited > 4096 or depth > 24:
            raise ValueError("journal payload node/depth budget exceeded")
        if isinstance(current, Mapping):
            if len(current) > 4096:
                raise ValueError("journal payload field budget exceeded")
            for key, child in current.items():
                if not isinstance(key, str) or len(key) > 256:
                    raise ValueError("journal JSON object keys must be bounded text")
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            if len(current) > 4096:
                raise ValueError("journal array budget exceeded")
            stack.extend((child, depth + 1) for child in current)
        elif current is None or isinstance(current, (str, bool, int)):
            if isinstance(current, str) and len(current) > 32768:
                raise ValueError("journal string budget exceeded")
        elif isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError("non-finite journal payload value")
        else:
            raise ValueError("non-JSON journal payload value")


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
        if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id) or kind not in ALLOWED:
            raise ValueError("invalid session or event kind")
        _validate_source_url(url)
        if isinstance(at, bool) or not isinstance(at, (int, float)) or not math.isfinite(at) or at < 0:
            raise ValueError("event time must be finite")
        # SQLite REAL round trips integers as floats. Hash persisted semantics.
        at = float(at)
        if payload is not None and not isinstance(payload, Mapping):
            raise ValueError("journal payload must be a JSON object")
        try:
            data = dict(payload) if payload is not None else {}
            _bounded_json_tree(data)
            encoded = _canonical(data)
            size = len(encoded.encode("utf-8", errors="strict"))
        except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
            raise ValueError("journal payload must be canonical finite JSON") from exc
        if size > 32768:
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
        # Stream rows from SQLite: journal verification must not materialize
        # the entire history in memory for long-lived companion sessions.
        cursor = self.db.execute(
            "SELECT sequence,event_id,kind,url,at,payload,previous_digest,digest "
            "FROM dragon_companion_events WHERE session_id=? ORDER BY sequence",
            (session_id,))
        for index, r in enumerate(cursor, 1):
            try:
                seq, event_id, kind, url, at, payload, parent, digest = r
                if (seq != index or parent != previous or event_id != digest
                        or kind not in ALLOWED or not math.isfinite(at)):
                    return False
                _validate_source_url(url)
                parsed_payload = json.loads(payload)
                if (not isinstance(parsed_payload, dict)
                        or _canonical(parsed_payload) != payload):
                    return False
                base = {"session_id": session_id, "sequence": seq, "kind": kind,
                        "url": url, "at": at, "payload": parsed_payload,
                        "previous_digest": parent}
                computed = hashlib.sha256(_canonical(base).encode("utf-8")).hexdigest()
                if computed != digest:
                    # Historical integer timestamp writers encoded timestamp
                    # as int before SQLite REAL round-trip. Preserve exact
                    # evidence without broadening any other chain field.
                    if not float(at).is_integer():
                        return False
                    base["at"] = int(at)
                    if hashlib.sha256(_canonical(base).encode("utf-8")).hexdigest() != digest:
                        return False
                previous = digest
            except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
                return False
        return True
