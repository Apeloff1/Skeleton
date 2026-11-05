"""Append-only, HMAC-bound private candidate training event ledger.

Requires a private SQLite file, external key custody and pinned head for
truncation evidence. Does not itself attest training rights or quality.
"""
from __future__ import annotations
import hashlib
import hmac
import sqlite3
from threading import RLock

from .strict import decode, encode, identity, sha
from .errors import deny

GENESIS = "0" * 64


class CandidateLedger:
    def __init__(self, db: sqlite3.Connection, *, key: bytes):
        if not isinstance(db, sqlite3.Connection):
            deny("ledger-database")
        if type(key) is not bytes or len(key) < 32:
            deny("ledger-key")
        self.db = db
        self.key = key
        self.lock = RLock()
        db.execute("""CREATE TABLE IF NOT EXISTS candidate_training_events(
            run_id TEXT NOT NULL, seq INTEGER NOT NULL,
            event_id TEXT NOT NULL, kind TEXT NOT NULL,
            record BLOB NOT NULL, previous_mac TEXT NOT NULL,
            mac TEXT NOT NULL, PRIMARY KEY(run_id,seq),
            UNIQUE(run_id,event_id))""")

    def _mac(self, run_id: str, seq: int, event_id: str, kind: str,
             record: bytes, previous: str) -> str:
        payload = {
            "schema": "skeleton.native-candidate.ledger-event.v1",
            "run_id": run_id, "sequence": seq, "event_id": event_id,
            "kind": kind, "record_sha256": hashlib.sha256(record).hexdigest(),
            "previous_mac": previous,
        }
        return hmac.new(self.key, encode(payload), hashlib.sha256).hexdigest()

    def append(self, run_id: str, event_id: str, kind: str, value: dict) -> dict:
        identity(run_id, "run")
        identity(event_id, "event")
        identity(kind, "event-kind")
        record = encode(value)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.verify(run_id)
                existing = self.db.execute(
                    """SELECT seq,kind,record FROM candidate_training_events
                    WHERE run_id=? AND event_id=?""", (run_id, event_id)
                ).fetchone()
                if existing is not None:
                    if existing[1] != kind or existing[2] != record:
                        deny("ledger-conflicting-replay")
                    self.db.execute("COMMIT")
                    return {"sequence": existing[0], "replayed": True}
                previous = self.db.execute(
                    """SELECT seq,mac FROM candidate_training_events
                    WHERE run_id=? ORDER BY seq DESC LIMIT 1""", (run_id,)
                ).fetchone()
                seq = 1 if previous is None else previous[0] + 1
                prev_mac = GENESIS if previous is None else previous[1]
                mac = self._mac(run_id, seq, event_id, kind, record, prev_mac)
                self.db.execute(
                    """INSERT INTO candidate_training_events
                    (run_id,seq,event_id,kind,record,previous_mac,mac)
                    VALUES(?,?,?,?,?,?,?)""",
                    (run_id, seq, event_id, kind, record, prev_mac, mac),
                )
                self.db.execute("COMMIT")
                return {"sequence": seq, "replayed": False, "head_mac": mac}
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def verify(self, run_id: str, *, expected_head: str | None = None) -> dict:
        identity(run_id, "run")
        rows = self.db.execute(
            """SELECT seq,event_id,kind,record,previous_mac,mac FROM candidate_training_events
            WHERE run_id=? ORDER BY seq""", (run_id,),
        ).fetchall()
        previous = GENESIS
        for index, (seq, event_id, kind, raw, prior, mac) in enumerate(rows, 1):
            if seq != index or prior != previous:
                deny("ledger-gap")
            if decode(raw) is None or encode(decode(raw)) != raw:
                deny("ledger-invalid-record")
            if not hmac.compare_digest(self._mac(run_id, seq, event_id,
                                                 kind, raw, prior), mac):
                deny("ledger-tamper")
            previous = mac
        if expected_head is not None:
            sha(expected_head, "pinned-head")
            if not hmac.compare_digest(previous, expected_head):
                deny("ledger-truncation")
        return {"run_id": run_id, "count": len(rows), "head_mac": previous,
                "verified": True, "release_certified": False}

    def replay(self, run_id: str) -> tuple[dict, ...]:
        self.verify(run_id)
        rows = self.db.execute(
            """SELECT event_id,kind,record FROM candidate_training_events
            WHERE run_id=? ORDER BY seq""", (run_id,)
        ).fetchall()
        return tuple({"id": id, "kind": kind, "value": decode(raw)}
                     for id, kind, raw in rows)
