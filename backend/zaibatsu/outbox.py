"""Persistent Zaibatsu outbox and retained event ledger.

The generic application outbox (core.durable_outbox) compacts confirmed rows.
This specialized journal retains fabric events and atomically commits their
chain head with delivery admission. SQLite is the local transactional boundary;
external effects remain at-least-once and require an idempotent sink.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator

GENESIS = "genesis"
MAX_RECORD_BYTES = 256 * 1024
MAX_STORE_BYTES = 128 * 1024 * 1024
MAX_RECORDS = 100_000
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", re.ASCII)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS counters (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    journaled INTEGER NOT NULL DEFAULT 0,
    confirmed INTEGER NOT NULL DEFAULT 0,
    fabric_seq INTEGER NOT NULL DEFAULT 0,
    fabric_head TEXT NOT NULL DEFAULT 'genesis'
);
INSERT OR IGNORE INTO counters(singleton) VALUES(1);
CREATE TABLE IF NOT EXISTS intents (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    collection TEXT NOT NULL,
    body TEXT NOT NULL,
    digest TEXT NOT NULL,
    delivery_id TEXT NOT NULL UNIQUE,
    created REAL NOT NULL,
    fabric_seq INTEGER UNIQUE,
    delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0,1)),
    attempts INTEGER NOT NULL DEFAULT 0,
    retry_at REAL NOT NULL DEFAULT 0,
    lease TEXT,
    lease_until REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS intents_pending ON intents(delivered,seq);
"""


class OutboxFull(RuntimeError):
    """No mutation was admitted because durable capacity was exhausted."""


class JournalIntegrityError(RuntimeError):
    """Custody could not be verified; do not publish or silently rebuild."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _name(value: str) -> str:
    if type(value) is not str or not _NAME.fullmatch(value):
        raise ValueError("invalid journal name")
    return value


def _body(document: dict) -> str:
    if type(document) is not dict or "_outbox_id" in document:
        raise ValueError("journal document must be an object without reserved delivery identity")
    result = canonical(document)
    if len(result) > MAX_RECORD_BYTES:
        raise OutboxFull("journal record exceeds byte budget")
    return result


@dataclass
class Intent:
    seq: int
    collection: str
    document: dict[str, Any]
    journaled_at: float = field(default_factory=time.time)
    confirmed: bool = False
    attempts: int = 0


class Outbox:
    """Bounded restart-safe journal with cross-process transaction admission.

    The sink receives a detached document with a reserved _outbox_id key.
    It must deduplicate by that identity, including across process restarts.
    A successful return of None or True confirms; False refuses the delivery.
    Files belong in an operator-owned local data directory, not on network FS.
    """

    def __init__(self, sink: Callable[[str, dict], Awaitable[None]], cap: int = 4096,
                 *, path: str | Path | None = None, record_cap: int = MAX_RECORDS,
                 byte_cap: int = MAX_STORE_BYTES, sink_timeout: float = 15.0):
        if not callable(sink) or type(cap) is not int or not 1 <= cap <= MAX_RECORDS:
            raise ValueError("invalid outbox sink or capacity")
        if type(record_cap) is not int or not cap <= record_cap <= MAX_RECORDS:
            raise ValueError("invalid retained record budget")
        if type(byte_cap) is not int or not 1024 <= byte_cap <= MAX_STORE_BYTES:
            raise ValueError("invalid retained byte budget")
        if not math.isfinite(sink_timeout) or not 0 < sink_timeout <= 60:
            raise ValueError("invalid sink timeout")
        self._sink = sink
        self._cap = cap
        self._record_cap = record_cap
        self._byte_cap = byte_cap
        self._timeout = sink_timeout
        self._lease_seconds = max(30.0, sink_timeout * 3)
        self._path = Path(path or os.environ.get("ZAIBATSU_OUTBOX_PATH") or
                          Path(__file__).resolve().parents[1] / "data" / "zaibatsu" / "events.sqlite3")
        if not self._path.is_absolute():
            self._path = self._path.absolute()
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self._path.is_symlink() or self._path.parent.is_symlink():
            raise JournalIntegrityError("symlinked journal location")
        self._lock = asyncio.Lock()
        with self._connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise JournalIntegrityError("unknown journal schema")
            if version == 0:
                tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                if tables:
                    raise JournalIntegrityError("unrecognized existing journal")
                db.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA + "\nPRAGMA user_version=1; COMMIT;")
            if db.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                raise JournalIntegrityError("journal database failed integrity check")
        self.verify_fabric()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=5000")
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self, *, write: bool = True) -> Iterator[sqlite3.Connection]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    @staticmethod
    def _checked(row: sqlite3.Row) -> dict:
        try:
            body = row["body"]
            if len(body) > MAX_RECORD_BYTES or not hmac.compare_digest(_sha(body), row["digest"]):
                raise JournalIntegrityError("journal record checksum mismatch")
            doc = json.loads(body)
            if _body(doc) != body:
                raise JournalIntegrityError("noncanonical journal record")
            return doc
        except (ValueError, TypeError, UnicodeError) as exc:
            raise JournalIntegrityError("invalid journal record") from exc

    def _admit(self, db: sqlite3.Connection, collection: str, body: str,
               fabric_seq: int | None = None) -> int:
        count, size, pending = db.execute(
            "SELECT count(*), coalesce(sum(length(body)),0), "
            "coalesce(sum(CASE WHEN delivered=0 THEN 1 ELSE 0 END),0) FROM intents"
        ).fetchone()
        if pending >= self._cap or count >= self._record_cap or size + len(body) > self._byte_cap:
            raise OutboxFull("durable journal backpressured; no record evicted")
        cur = db.execute(
            "INSERT INTO intents(collection,body,digest,delivery_id,created,fabric_seq) VALUES(?,?,?,?,?,?)",
            (collection, body, _sha(body), uuid.uuid4().hex, time.time(), fabric_seq),
        )
        db.execute("UPDATE counters SET journaled=journaled+1 WHERE singleton=1")
        return int(cur.lastrowid)

    async def journal(self, collection: str, document: dict[str, Any]) -> int:
        collection = _name(collection)
        if collection == "omega_fabric":
            raise ValueError("fabric records require atomic fabric admission")
        body = _body(document)
        # This bounded transaction contains no await: cancellation cannot
        # split durable admission from its returned sequence in this task.
        with self._transaction() as db:
            return self._admit(db, collection, body)

    def append_fabric(self, factory: Callable[[int, str], dict]) -> dict:
        from .fabric import validate_event
        with self._transaction() as db:
            seq, head = db.execute(
                "SELECT fabric_seq,fabric_head FROM counters WHERE singleton=1"
            ).fetchone()
            prior = db.execute(
                "SELECT * FROM intents WHERE fabric_seq IS NOT NULL ORDER BY fabric_seq DESC LIMIT 1"
            ).fetchone()
            if prior is None:
                if seq or head != GENESIS:
                    raise JournalIntegrityError("missing fabric chain")
            else:
                last = self._checked(prior)
                validate_event(last)
                if last["seq"] != seq or last["hash"] != head:
                    raise JournalIntegrityError("fabric head mismatch")
            doc = factory(seq + 1, head)
            validate_event(doc, seq=seq + 1, prev=head)
            body = _body(doc)
            self._admit(db, "omega_fabric", body, seq + 1)
            db.execute("UPDATE counters SET fabric_seq=?,fabric_head=? WHERE singleton=1",
                       (seq + 1, doc["hash"]))
            return json.loads(body)

    def verify_fabric(self) -> bool:
        from .fabric import validate_event
        with self._transaction(write=False) as db:
            seq, prev = 0, GENESIS
            for row in db.execute("SELECT * FROM intents WHERE fabric_seq IS NOT NULL ORDER BY fabric_seq"):
                doc = self._checked(row)
                seq += 1
                validate_event(doc, seq=seq, prev=prev)
                if row["fabric_seq"] != seq or row["collection"] != "omega_fabric":
                    raise JournalIntegrityError("fabric row identity mismatch")
                prev = doc["hash"]
            state = db.execute("SELECT fabric_seq,fabric_head FROM counters WHERE singleton=1").fetchone()
            if tuple(state) != (seq, prev):
                raise JournalIntegrityError("fabric checkpoint mismatch")
        return True

    def fabric_tail(self, ledger: str, limit: int, hot_cap: int) -> list[dict]:
        with self._transaction(write=False) as db:
            rows = db.execute(
                "SELECT * FROM intents WHERE fabric_seq IS NOT NULL "
                "ORDER BY fabric_seq DESC LIMIT ?", (hot_cap,)
            )
            result = []
            from .fabric import validate_event
            for row in rows:
                doc = self._checked(row)
                validate_event(doc)
                if doc["ledger"] == ledger:
                    result.append(doc)
                    if len(result) >= limit:
                        break
            return result

    def _claim(self) -> tuple[sqlite3.Row, str] | None:
        now = time.time()
        with self._transaction() as db:
            row = db.execute("SELECT * FROM intents WHERE delivered=0 ORDER BY seq LIMIT 1").fetchone()
            if row is None or row["retry_at"] > now or row["lease_until"] > now:
                return None
            self._checked(row)
            lease = uuid.uuid4().hex
            db.execute("UPDATE intents SET lease=?,lease_until=?,attempts=attempts+1 WHERE seq=?",
                       (lease, now + self._lease_seconds, row["seq"]))
            return row, lease

    def _finish(self, row: sqlite3.Row, lease: str, success: bool) -> bool:
        with self._transaction() as db:
            current = db.execute("SELECT * FROM intents WHERE seq=? AND lease=? AND delivered=0",
                                 (row["seq"], lease)).fetchone()
            if current is None:
                return False
            if success:
                if current["fabric_seq"] is None:
                    db.execute("DELETE FROM intents WHERE seq=?", (row["seq"],))
                else:
                    db.execute("UPDATE intents SET delivered=1,lease=NULL,lease_until=0 WHERE seq=?",
                               (row["seq"],))
                db.execute("UPDATE counters SET confirmed=confirmed+1 WHERE singleton=1")
            else:
                delay = min(300, 2 ** min(current["attempts"], 8))
                db.execute("UPDATE intents SET lease=NULL,lease_until=0,retry_at=? WHERE seq=?",
                           (time.time() + delay, row["seq"]))
            return success

    async def reconcile(self, limit: int = 128) -> int:
        if type(limit) is not int or not 1 <= limit <= 4096:
            raise ValueError("invalid reconciliation limit")
        done = 0
        async with self._lock:
            for _ in range(limit):
                claim = self._claim()
                if claim is None:
                    break
                row, lease = claim
                document = self._checked(row)
                document["_outbox_id"] = row["delivery_id"]
                try:
                    result = await asyncio.wait_for(self._sink(row["collection"], document), timeout=self._timeout)
                    success = result is not False
                except asyncio.CancelledError:
                    self._finish(row, lease, False)
                    raise
                except Exception:
                    success = False
                if not self._finish(row, lease, success):
                    break
                done += 1
        return done

    async def pending_count(self) -> int:
        with self._connect() as db:
            return db.execute("SELECT count(*) FROM intents WHERE delivered=0").fetchone()[0]

    def health(self) -> dict:
        with self._transaction(write=False) as db:
            journaled, confirmed, seq, head = db.execute(
                "SELECT journaled,confirmed,fabric_seq,fabric_head FROM counters WHERE singleton=1"
            ).fetchone()
            retained, pending, size = db.execute(
                "SELECT count(*),coalesce(sum(CASE WHEN delivered=0 THEN 1 ELSE 0 END),0),"
                "coalesce(sum(length(body)),0) FROM intents"
            ).fetchone()
            return {"journaled_total": journaled, "confirmed_total": confirmed,
                    "pending": pending, "retained_records": retained, "retained_bytes": size,
                    "fabric_seq": seq, "fabric_head": head, "delivery": "at_least_once",
                    "capacity": self._cap, "record_cap": self._record_cap,
                    "byte_cap": self._byte_cap}

    @property
    def journaled_total(self) -> int:
        return self.health()["journaled_total"]

    @property
    def confirmed_total(self) -> int:
        return self.health()["confirmed_total"]


async def run_reconciler(outbox: Outbox, interval_secs: float = 5.0) -> None:
    if not math.isfinite(interval_secs) or not 0 < interval_secs <= 3600:
        raise ValueError("invalid reconciliation interval")
    while True:
        await outbox.reconcile()
        await asyncio.sleep(interval_secs)
