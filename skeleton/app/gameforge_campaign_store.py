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
from skeleton.app.original_quest_cli import _encode, _integer

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

    _namespace = "campaign"
    _play = staticmethod(play_campaign)
    _verify = staticmethod(verify_session)
    _append = staticmethod(append_actions)

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        # Only the fixed compile-time namespaces are allowed. Neither SQL
        # identifiers nor statements can be selected by JSON input.
        _check(self._namespace in {"campaign", "expedition", "saga"}, "unknown journal namespace")
        return self.db.execute(sql.replace("gf_campaign_", "gf_" + self._namespace + "_"), params)

    def __init__(self, db: sqlite3.Connection, *, initialize: bool = True) -> None:
        _check(isinstance(db, sqlite3.Connection), "SQLite connection required")
        self.db = db
        _check(self._namespace in {"campaign", "expedition", "saga"}, "unknown journal namespace")
        _check(not db.in_transaction, "store requires its own transaction boundary")
        db.execute("PRAGMA foreign_keys = ON")
        _check(db.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "foreign keys unavailable")
        if not initialize:
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type=\'table\' AND name IN (?,?)", ("gf_" + self._namespace + "_slots_v1", "gf_" + self._namespace + "_revisions_v1"))}
            _check(names == {"gf_" + self._namespace + "_slots_v1", "gf_" + self._namespace + "_revisions_v1"}, "campaign journal schema missing")
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
        self._execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _slot(self, slot: str, source: Any) -> int:
        row = self._execute(
            "SELECT source_digest, head FROM gf_campaign_slots_v1 WHERE slot=?", (slot,)
        ).fetchone()
        _check(row is not None and row[0] == digest(source), "missing slot or independent source mismatch")
        head = _integer(row[1], 0, MAX_REVISIONS - 1)
        count, maximum = self._execute(
            "SELECT COUNT(*), MAX(revision) FROM gf_campaign_revisions_v1 WHERE slot=?", (slot,)
        ).fetchone()
        _check(count == head + 1 and maximum == head, "slot head and journal disagree")
        return head

    def _row(self, slot: str, revision: int) -> tuple:
        row = self._execute("""
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
        _check(type(receipt) is dict and _encode(receipt) == raw and receipt.get("session_digest") == receipt_hash
               and self._verify(source, receipt), "stored checkpoint replay mismatch")
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
        result = {"slot": slot, "revision": revision, "operation": row[1],
                  "receipt": receipt, "native_qualified": False, "release_qualified": False}
        _encode(result)  # Reject oversized response before a write transaction commits.
        return result

    def _capacity(self, slot: str, raw: bytes) -> None:
        slot_bytes = self._execute(
            "SELECT COALESCE(SUM(length(receipt)),0) FROM gf_campaign_revisions_v1 WHERE slot=?",
            (slot,)
        ).fetchone()[0]
        total = self._execute(
            "SELECT COALESCE(SUM(length(receipt)),0) FROM gf_campaign_revisions_v1"
        ).fetchone()[0]
        _check(slot_bytes + len(raw) <= MAX_SLOT_BYTES and total + len(raw) <= MAX_TOTAL_BYTES,
               "logical receipt storage ceiling exceeded")

    def _insert(self, slot: str, revision: int, operation: str, request_hash: str,
                previous: str | None, receipt: dict) -> None:
        raw = _encode(receipt)
        self._capacity(slot, raw)
        self._execute("""
            INSERT INTO gf_campaign_revisions_v1
            (slot, revision, operation, request_digest, previous_digest, receipt_digest, receipt)
            VALUES (?,?,?,?,?,?,?)
        """, (slot, revision, operation, request_hash, previous, receipt["session_digest"], raw))

    def _retry(self, slot: str, operation: str, request_hash: str, source: Any, head: int) -> dict | None:
        prior = self._execute("""
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
            exists = self._execute(
                "SELECT 1 FROM gf_campaign_slots_v1 WHERE slot=?", (slot,)
            ).fetchone()
            if exists:
                head = self._slot(slot, source)
                replay = self._retry(slot, operation, request_hash, source, head)
                if replay is not None:
                    return replay
                raise RevisionConflict("slot already exists")
            count = self._execute("SELECT COUNT(*) FROM gf_campaign_slots_v1").fetchone()[0]
            _check(count < MAX_SLOTS, "slot ceiling exceeded")
            receipt = self._play(source, [])
            self._execute(
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
            receipt = self._append(source, prior, additional)
            self._insert(slot, head + 1, operation, request_hash, prior["session_digest"], receipt)
            updated = self._execute(
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

    def fork(self, parent_slot: str, source: Any, parent_revision: int,
             expected_digest: str, child_slot: str) -> dict:
        """Atomically copy a verified historical prefix to a new independent slot.

        Existing operation identities are scoped by slot and copied intact.
        No original revision is deleted or rewritten. The returned ancestry
        is an observation of this transaction, not a separately signed ledger.
        Repeated forks to an existing child are rejected rather than inferred.
        """
        parent, child = _identity(parent_slot), _identity(child_slot)
        _check(parent != child, "fork must use a distinct slot")
        _check(type(expected_digest) is str and re.fullmatch("[0-9a-f]{64}", expected_digest) is not None,
               "expected parent receipt digest required")
        source_hash = digest(source)
        with self._transaction():
            head = self._slot(parent, source)
            chosen = _integer(parent_revision, 0, head)
            _check(self._execute("SELECT 1 FROM gf_campaign_slots_v1 WHERE slot=?", (child,)).fetchone()
                   is None, "fork destination already exists")
            _check(self._execute("SELECT COUNT(*) FROM gf_campaign_slots_v1").fetchone()[0] < MAX_SLOTS,
                   "slot ceiling exceeded")
            selected = self._verified(parent, source, chosen)
            if selected["receipt"]["session_digest"] != expected_digest:
                raise RevisionConflict("parent checkpoint digest mismatch")
            total = 0
            # Copy only the verified prefix, never the old branch's future.
            self._execute(
                "INSERT INTO gf_campaign_slots_v1(slot,source_digest,head) VALUES(?,?,?)",
                (child, source_hash, chosen)
            )
            for revision in range(chosen + 1):
                row = self._row(parent, revision)
                receipt = self._verified(parent, source, revision)["receipt"]
                total += len(row[5])
                _check(total <= MAX_SLOT_BYTES, "fork prefix exceeds source byte ceiling")
                self._insert(child, revision, row[1], row[2], row[3], receipt)
            copied = self._verified(child, source, chosen)
            _check(copied["receipt"] == selected["receipt"], "fork replay differs")
            result = {"parent_slot": parent, "parent_revision": chosen,
                      "parent_receipt_digest": expected_digest, "child": copied,
                      "native_qualified": False, "release_qualified": False}
            _encode(result)
            return result

    def snapshot(self, slot: str, source: Any) -> dict:
        """Export a compact operation ledger; every historical receipt is replayed.

        Only suffix actions and operation identities are retained in the
        portable form, rather than repeatedly embedding complete checkpoints.
        """
        slot = _identity(slot)
        with self._transaction(write=False):
            head = self._slot(slot, source)
            operations = []
            prefix = []
            retained = 0
            for revision in range(head + 1):
                row = self._row(slot, revision)
                verified = self._verified(slot, source, revision)["receipt"]
                retained += len(row[5])
                _check(retained <= MAX_SLOT_BYTES, "snapshot exceeds stored byte ceiling")
                actions = verified["actions"]
                operations.append({
                    "operation": row[1], "additional": actions[len(prefix):],
                    "receipt_digest": verified["session_digest"],
                })
                prefix = actions
            body = {"schema": "skeleton.gameforge.revision_archive.v1",
                    "namespace": self._namespace, "source_digest": digest(source),
                    "origin_slot": slot, "head": head, "operations": operations,
                    "native_qualified": False, "release_qualified": False}
            result = {**body, "archive_digest": digest(body)}
            _encode({"request": source, "archive": result})
            return result

    def restore(self, slot: str, source: Any, archive: Any) -> dict:
        """Atomically reconstruct an archived operation ledger in a new slot.

        The archive cannot select a different runtime adapter, and all
        claimed revision digests must match independent owner replay.
        """
        slot = _identity(slot)
        _encode({"request": source, "archive": archive})
        _check(type(archive) is dict and set(archive) == {
            "schema", "namespace", "source_digest", "origin_slot", "head",
            "operations", "native_qualified", "release_qualified", "archive_digest",
        }, "invalid revision archive shape")
        _check(archive["schema"] == "skeleton.gameforge.revision_archive.v1"
               and archive["namespace"] == self._namespace
               and archive["source_digest"] == digest(source)
               and archive["native_qualified"] is False
               and archive["release_qualified"] is False, "revision archive authority mismatch")
        _identity(archive["origin_slot"])
        _check(archive["archive_digest"] == digest({
            key: value for key, value in archive.items() if key != "archive_digest"
        }), "archive digest mismatch")
        head = _integer(archive["head"], 0, MAX_REVISIONS - 1)
        operations = archive["operations"]
        _check(type(operations) is list and len(operations) == head + 1,
               "archive count and head mismatch")
        seen = set()
        for revision, row in enumerate(operations):
            _check(type(row) is dict and set(row) == {"operation", "additional", "receipt_digest"},
                   "invalid archive operation")
            operation = _identity(row["operation"])
            _check(operation not in seen, "duplicate archived operation")
            seen.add(operation)
            _check(type(row["additional"]) is list
                   and bool(row["additional"]) == bool(revision), "invalid archived action suffix")
            _check(type(row["receipt_digest"]) is str
                   and re.fullmatch("[0-9a-f]{64}", row["receipt_digest"]) is not None,
                   "invalid archived receipt digest")
        source_hash = digest(source)
        with self._transaction():
            _check(self._execute("SELECT 1 FROM gf_campaign_slots_v1 WHERE slot=?", (slot,)).fetchone()
                   is None, "restore destination already exists")
            _check(self._execute("SELECT COUNT(*) FROM gf_campaign_slots_v1").fetchone()[0] < MAX_SLOTS,
                   "slot ceiling exceeded")
            self._execute("INSERT INTO gf_campaign_slots_v1(slot,source_digest,head) VALUES(?,?,?)",
                          (slot, source_hash, head))
            receipt = None
            for revision, row in enumerate(operations):
                if revision == 0:
                    receipt = self._play(source, [])
                    previous = None
                    request_hash = digest({"kind": "create", "source_digest": source_hash})
                else:
                    assert receipt is not None
                    previous = receipt["session_digest"]
                    receipt = self._append(source, receipt, row["additional"])
                    request_hash = digest({"kind": "append", "source_digest": source_hash,
                                           "expected_revision": revision - 1,
                                           "additional": row["additional"]})
                _check(receipt["session_digest"] == row["receipt_digest"],
                       "archived checkpoint differs from independent replay")
                self._insert(slot, revision, row["operation"], request_hash, previous, receipt)
            result = self._verified(slot, source, head)
            _encode(result)
            return result

    def history(self, slot: str, source: Any) -> dict:
        """Audit the complete bounded chain from genesis, not just the current pair."""
        slot = _identity(slot)
        with self._transaction(write=False):
            head = self._slot(slot, source)
            rows = self._execute("""
                SELECT revision, operation, request_digest, previous_digest, receipt_digest,
                       CASE WHEN length(receipt) <= 2097152 THEN receipt ELSE NULL END
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
