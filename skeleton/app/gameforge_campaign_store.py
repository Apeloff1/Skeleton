"""SQLite custody for source-bound GameForge campaign revisions.

A caller supplies a private local SQLite connection. The database is a
revision journal, not an identity authority or a substitute for independent
source. All returned checkpoints are independently replayed. Each mutation
has a bounded operation identity, an expected revision and atomic commit.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import re
import sqlite3
from typing import Any, Iterator

from skeleton.app.gameforge_campaign import (
    append_actions, digest, play_campaign, verify_session,
)
from skeleton.app.original_quest_cli import _encode, _integer, _require

MAX_SLOTS = 128
MAX_REVISIONS = 256
MAX_SLOT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}\Z")


class CampaignStoreError(ValueError):
    """Storage authority or revision admission failed."""


class RevisionConflict(CampaignStoreError):
    """The checkpoint changed or the operation identity was reused."""


def _identity(value: Any) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise CampaignStoreError("invalid slot or operation identity")
    return value


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise CampaignStoreError(message)


class CampaignStore:
    """Single private SQLite workspace, with independent request on every call."""

    def __init__(self, db: sqlite3.Connection, *, initialize: bool = True) -> None:
        _check(isinstance(db, sqlite3.Connection), "SQLite connection required")
        self.db = db
        _check(not db.in_transaction, "store requires its own transaction boundary")
        db.execute("PRAGMA foreign_keys = ON")
        _check(db.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "foreign keys unavailable")
        if not initialize:
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type=\'table\' AND name IN (?,?)", ("gf_campaign_slots_v1", "gf_campaign_revisions_v1"))}
            _check(names == {"gf_campaign_slots_v1", "gf_campaign_revisions_v1"}, "campaign journal schema missing")
            return
        with self._transaction():
            db.execute("""
                CREATE TABLE IF NOT EXISTS gf_campaign_slots_v1 (
                    slot TEXT PRIMARY KEY,
                    source_digest TEXT NOT NULL,
                    head INTEGER NOT NULL CHECK(head >= 0)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS gf_campaign_revisions_v1 (
                    slot TEXT NOT NULL REFERENCES gf_campaign_slots_v1(slot),
                    revision INTEGER NOT NULL CHECK(revision >= 0),
                    operation TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    previous_digest TEXT,
                    receipt_digest TEXT NOT NULL,
                    receipt BLOB NOT NULL,
                    PRIMARY KEY(slot, revision),
                    UNIQUE(slot, operation)
                )
            """)

    @contextmanager
    def _transaction(self, *, write: bool = True) -> Iterator[None]:
        _check(not self.db.in_transaction, "nested store transaction forbidden")
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _slot(self, slot: str, source: Any) -> int:
        row = self.db.execute(
            "SELECT source_digest, head FROM gf_campaign_slots_v1 WHERE slot=?", (slot,)
        ).fetchone()
        _check(row is not None and row[0] == digest(source), "missing slot or independent source mismatch")
        return _integer(row[1], 0, MAX_REVISIONS - 1)

    def _row(self, slot: str, revision: int) -> tuple:
        row = self.db.execute("""
            SELECT revision, operation, request_digest, previous_digest, receipt_digest,
                   CASE WHEN length(receipt) <= 2097152 THEN receipt ELSE NULL END
            FROM gf_campaign_revisions_v1 WHERE slot=? AND revision=?
        """, (slot, revision)).fetchone()
        _check(row is not None, "revision missing")
        return row

    def _decode(self, source: Any, row: tuple) -> dict:
        revision, operation, request_hash, previous, receipt_hash, raw = row
        _integer(revision, 0, MAX_REVISIONS - 1)
        _identity(operation)
        _check(type(request_hash) is str and re.fullmatch("[0-9a-f]{64}", request_hash) is not None,
               "invalid operation digest")
        _check(type(raw) is bytes and len(raw) <= 2 * 1024 * 1024, "invalid stored receipt bytes")
        try:
            receipt = json.loads(raw.decode("ascii"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise CampaignStoreError("stored receipt cannot be decoded") from exc
        _check(_encode(receipt) == raw and receipt.get("session_digest") == receipt_hash
               and verify_session(source, receipt), "stored checkpoint replay mismatch")
        _check((revision == 0 and previous is None and receipt["actions"] == [])
               or (revision > 0 and type(previous) is str and len(previous) == 64),
               "invalid checkpoint lineage shape")
        return receipt

    def _verified(self, slot: str, source: Any, revision: int) -> dict:
        row = self._row(slot, revision)
        receipt = self._decode(source, row)
        if revision == 0:
            expected = digest({"kind": "create", "source_digest": digest(source)})
            _check(row[2] == expected, "genesis request mismatch")
        else:
            parent = self._row(slot, revision - 1)
            prior = self._decode(source, parent)
            prefix = prior["actions"]
            actions = receipt["actions"]
            _check(row[3] == prior["session_digest"]
                   and len(actions) > len(prefix) and actions[:len(prefix)] == prefix,
                   "checkpoint does not append to predecessor")
            expected = digest({"kind": "append", "source_digest": digest(source),
                               "expected_revision": revision - 1,
                               "additional": actions[len(prefix):]})
            _check(row[2] == expected, "stored append request mismatch")
        return {"slot": slot, "revision": revision, "operation": row[1],
                "receipt": receipt, "native_qualified": False, "release_qualified": False}

    def _capacity(self, slot: str, raw: bytes) -> None:
        slot_bytes = self.db.execute(
            "SELECT COALESCE(SUM(length(receipt)),0) FROM gf_campaign_revisions_v1 WHERE slot=?",
            (slot,)
        ).fetchone()[0]
        total = self.db.execute(
            "SELECT COALESCE(SUM(length(receipt)),0) FROM gf_campaign_revisions_v1"
        ).fetchone()[0]
        _check(slot_bytes + len(raw) <= MAX_SLOT_BYTES and total + len(raw) <= MAX_TOTAL_BYTES,
               "logical receipt storage ceiling exceeded")

    def _insert(self, slot: str, revision: int, operation: str, request_hash: str,
                previous: str | None, receipt: dict) -> None:
        raw = _encode(receipt)
        self._capacity(slot, raw)
        self.db.execute("""
            INSERT INTO gf_campaign_revisions_v1
            (slot, revision, operation, request_digest, previous_digest, receipt_digest, receipt)
            VALUES (?,?,?,?,?,?,?)
        """, (slot, revision, operation, request_hash, previous, receipt["session_digest"], raw))

    def _retry(self, slot: str, operation: str, request_hash: str, source: Any, head: int) -> dict | None:
        prior = self.db.execute("""
            SELECT revision, request_digest FROM gf_campaign_revisions_v1
            WHERE slot=? AND operation=?
        """, (slot, operation)).fetchone()
        if prior is None:
            return None
        if prior[1] != request_hash:
            raise RevisionConflict("operation identity already used with different input")
        _check(0 <= prior[0] <= head, "operation revision beyond slot head")
        return self._verified(slot, source, prior[0])

    def create(self, slot: str, source: Any, operation: str) -> dict:
        slot, operation = _identity(slot), _identity(operation)
        source_hash = digest(source)
        request_hash = digest({"kind": "create", "source_digest": source_hash})
        with self._transaction():
            exists = self.db.execute(
                "SELECT 1 FROM gf_campaign_slots_v1 WHERE slot=?", (slot,)
            ).fetchone()
            if exists:
                head = self._slot(slot, source)
                replay = self._retry(slot, operation, request_hash, source, head)
                if replay is not None:
                    return replay
                raise RevisionConflict("slot already exists")
            count = self.db.execute("SELECT COUNT(*) FROM gf_campaign_slots_v1").fetchone()[0]
            _check(count < MAX_SLOTS, "slot ceiling exceeded")
            receipt = play_campaign(source, [])
            self.db.execute(
                "INSERT INTO gf_campaign_slots_v1(slot,source_digest,head) VALUES(?,?,0)",
                (slot, source_hash)
            )
            self._insert(slot, 0, operation, request_hash, None, receipt)
            return self._verified(slot, source, 0)

    def append(self, slot: str, source: Any, expected_revision: int,
               operation: str, additional: Any) -> dict:
        slot, operation = _identity(slot), _identity(operation)
        expected = _integer(expected_revision, 0, MAX_REVISIONS - 1)
        _check(type(additional) is list and bool(additional), "nonempty action append required")
        request_hash = digest({"kind": "append", "source_digest": digest(source),
                               "expected_revision": expected, "additional": additional})
        with self._transaction():
            head = self._slot(slot, source)
            replay = self._retry(slot, operation, request_hash, source, head)
            if replay is not None:
                return replay
            if head != expected:
                raise RevisionConflict("expected revision is not current")
            _check(head + 1 < MAX_REVISIONS, "revision ceiling exceeded")
            prior = self._verified(slot, source, head)["receipt"]
            receipt = append_actions(source, prior, additional)
            self._insert(slot, head + 1, operation, request_hash, prior["session_digest"], receipt)
            updated = self.db.execute(
                "UPDATE gf_campaign_slots_v1 SET head=? WHERE slot=? AND head=?",
                (head + 1, slot, head)
            )
            if updated.rowcount != 1:
                raise RevisionConflict("checkpoint compare-and-swap failed")
            return self._verified(slot, source, head + 1)

    def read(self, slot: str, source: Any, revision: int | None = None) -> dict:
        slot = _identity(slot)
        with self._transaction(write=False):
            head = self._slot(slot, source)
            chosen = head if revision is None else _integer(revision, 0, head)
            return self._verified(slot, source, chosen)

    def history(self, slot: str, source: Any) -> dict:
        """Audit the complete bounded chain from genesis, not just the current pair."""
        slot = _identity(slot)
        with self._transaction(write=False):
            head = self._slot(slot, source)
            rows = self.db.execute("""
                SELECT revision, operation, request_digest, previous_digest, receipt_digest, receipt
                FROM gf_campaign_revisions_v1 WHERE slot=? ORDER BY revision
            """, (slot,))
            count = 0
            retained_bytes = 0
            previous = None
            entries = []
            for revision, row in enumerate(rows):
                count += 1
                _check(count <= head + 1 and count <= MAX_REVISIONS, "revision count and head mismatch")
                _check(type(row[5]) is bytes, "invalid history receipt bytes")
                retained_bytes += len(row[5])
                _check(retained_bytes <= MAX_SLOT_BYTES, "history exceeds logical byte limit")
                _check(row[0] == revision, "noncontiguous revision chain")
                receipt = self._decode(source, row)
                if previous is None:
                    expected = digest({"kind": "create", "source_digest": digest(source)})
                else:
                    prefix = previous["actions"]
                    actions = receipt["actions"]
                    _check(row[3] == previous["session_digest"] and len(actions) > len(prefix)
                           and actions[:len(prefix)] == prefix, "history is not append-only")
                    expected = digest({"kind": "append", "source_digest": digest(source),
                                       "expected_revision": revision - 1,
                                       "additional": actions[len(prefix):]})
                _check(row[2] == expected, "history operation binding mismatch")
                entries.append({"revision": revision, "operation": row[1],
                                "receipt_digest": receipt["session_digest"],
                                "action_count": len(receipt["actions"])})
                previous = receipt
            _check(count == head + 1, "revision count and head mismatch")
            return {"slot": slot, "head": head, "revisions": entries,
                    "native_qualified": False, "release_qualified": False}
