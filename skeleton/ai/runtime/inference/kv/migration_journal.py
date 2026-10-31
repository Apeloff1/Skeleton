"""Write-ahead custody for bounded, potentially partial KV tier migrations.

A RUNNING migration may already have moved physical pages. It is never
automatically retried after process failure. This journal contains page
identifiers and receipts, never KV tensors, prompts or backend handles.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import hmac
import json
import sqlite3
from threading import RLock

from .live_tier_controller import KVLiveTierController
from .pressure_tiering import TierApplyReceipt, TierPlan

SCHEMA = "skeleton.ai.kv-migration-journal.v1"
TABLE = "local_kv_migration_journal"
MAX_ROWS = 10_000
MAX_RECEIPT_BYTES = 8192
MAX_MOVES = 128


class KVMigrationOutcomeUnknown(RuntimeError):
    """Physical migration may have partially completed; no automatic retry."""


def _hex(value: object, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
        c not in "0123456789abcdef" for c in value
    ):
        raise ValueError("invalid " + label)
    return value


def _encode(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid migration journal encoding") from exc
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise ValueError("migration journal payload exceeds byte budget")
    return encoded


def _sign(key: bytes, body: object) -> str:
    return hmac.new(key, _encode(body), sha256).hexdigest()


def _plan_body(plan: TierPlan, session_id: str) -> dict[str, object]:
    if not isinstance(plan, TierPlan):
        raise ValueError("canonical tier migration plan required")
    _hex(plan.digest, "plan digest")
    _hex(plan.inventory_digest, "inventory digest")
    if len(plan.moves) > MAX_MOVES:
        raise ValueError("unbounded migration plan")
    return {
        "schema": SCHEMA,
        "session_id": session_id,
        "plan_digest": plan.digest,
        "inventory_digest": plan.inventory_digest,
        "moves": [asdict(move) for move in plan.moves],
    }


def _receipt_body(plan: TierPlan, receipt: TierApplyReceipt) -> dict[str, object]:
    if not isinstance(receipt, TierApplyReceipt):
        raise ValueError("canonical tier receipt required")
    if receipt.plan_digest != plan.digest:
        raise ValueError("migration receipt plan mismatch")
    keys = [move.page_key for move in plan.moves]
    moved = list(receipt.moved)
    rejected = [key for key, _ in receipt.rejected]
    if (
        len(set(keys)) != len(keys)
        or len(set(moved + rejected)) != len(moved) + len(rejected)
        or set(moved + rejected) != set(keys)
        or any(type(reason) is not str or not 1 <= len(reason) <= 128
               for _, reason in receipt.rejected)
    ):
        raise ValueError("migration receipt does not account for every move")
    body = {
        "schema": "skeleton.ai.kv-pressure-apply.v1",
        "plan_digest": plan.digest,
        "moved": moved,
        "rejected": [list(item) for item in receipt.rejected],
    }
    expected = sha256(_encode(body)).hexdigest()
    if not hmac.compare_digest(_hex(receipt.digest, "receipt digest"), expected):
        raise ValueError("migration receipt integrity mismatch")
    return body


class KVMigrationJournal:
    """Exclusive SQLite intent journal with authenticated committed receipts."""

    def __init__(
        self, connection: sqlite3.Connection, *,
        session_id: str, journal_key: bytes,
    ) -> None:
        if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
            raise ValueError("exclusive idle SQLite journal connection required")
        if type(journal_key) is not bytes or not 32 <= len(journal_key) <= 128:
            raise ValueError("independent migration journal key required")
        self.session_id = _hex(session_id, "session")
        self._key = journal_key
        self._connection = connection
        self._lock = RLock()
        connection.execute(
            "CREATE TABLE IF NOT EXISTS " + TABLE + " ("
            "plan_digest TEXT PRIMARY KEY NOT NULL,"
            "session_id TEXT NOT NULL,"
            "inventory_digest TEXT NOT NULL,"
            "plan_payload BLOB NOT NULL,"
            "plan_mac TEXT NOT NULL,"
            "state TEXT NOT NULL CHECK(state IN ('running','committed')),"
            "receipt_payload BLOB,"
            "receipt_mac TEXT"
            ") WITHOUT ROWID"
        )
        columns = tuple(row[1] for row in connection.execute(
            "PRAGMA table_info(" + TABLE + ")"
        ))
        if columns != (
            "plan_digest", "session_id", "inventory_digest",
            "plan_payload", "plan_mac", "state", "receipt_payload", "receipt_mac",
        ):
            raise ValueError("untrusted KV migration journal schema")

    def _begin(self) -> None:
        if self._connection.in_transaction:
            raise KVMigrationOutcomeUnknown("migration journal has active transaction")
        self._connection.execute("BEGIN IMMEDIATE")

    def begin(self, plan: TierPlan) -> None:
        """Commit intent before touching the physical KV storage adapter."""
        body = _plan_body(plan, self.session_id)
        payload = _encode(body)
        mac = _sign(self._key, body)
        with self._lock:
            self._begin()
            try:
                if self._connection.execute(
                    "SELECT 1 FROM " + TABLE + " WHERE state = 'running' LIMIT 1"
                ).fetchone():
                    raise KVMigrationOutcomeUnknown(
                        "unresolved physical migration blocks new work"
                    )
                if self._connection.execute(
                    "SELECT 1 FROM " + TABLE + " WHERE plan_digest = ?",
                    (plan.digest,),
                ).fetchone():
                    raise KVMigrationOutcomeUnknown("migration plan already consumed")
                count = self._connection.execute(
                    "SELECT COUNT(*) FROM " + TABLE
                ).fetchone()[0]
                if count >= MAX_ROWS:
                    raise KVMigrationOutcomeUnknown("migration journal capacity exhausted")
                self._connection.execute(
                    "INSERT INTO " + TABLE
                    + " (plan_digest, session_id, inventory_digest,"
                    + " plan_payload, plan_mac, state)"
                    + " VALUES (?, ?, ?, ?, ?, 'running')",
                    (plan.digest, self.session_id, plan.inventory_digest, payload, mac),
                )
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def commit(self, plan: TierPlan, receipt: TierApplyReceipt) -> None:
        """Authenticate a complete per-move result, including partial failures."""
        body = _receipt_body(plan, receipt)
        payload = _encode(body)
        mac = _sign(self._key, body)
        expected_plan = _encode(_plan_body(plan, self.session_id))
        with self._lock:
            self._begin()
            try:
                row = self._connection.execute(
                    "SELECT session_id, inventory_digest, plan_payload,"
                    " plan_mac, state, receipt_payload, receipt_mac FROM "
                    + TABLE + " WHERE plan_digest = ?",
                    (plan.digest,),
                ).fetchone()
                if (
                    row is None
                    or row[0] != self.session_id
                    or row[1] != plan.inventory_digest
                    or row[2] != expected_plan
                    or type(row[3]) is not str
                    or not hmac.compare_digest(
                        _hex(row[3], "plan MAC"),
                        _sign(self._key, _plan_body(plan, self.session_id)),
                    )
                    or row[4:] != ("running", None, None)
                ):
                    raise KVMigrationOutcomeUnknown("migration intent is missing or forged")
                changed = self._connection.execute(
                    "UPDATE " + TABLE
                    + " SET state = 'committed', receipt_payload = ?, receipt_mac = ?"
                    + " WHERE plan_digest = ? AND state = 'running'",
                    (payload, mac, plan.digest),
                ).rowcount
                if changed != 1:
                    raise KVMigrationOutcomeUnknown("migration journal CAS failed")
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def recover_committed(self, plan: TierPlan) -> dict[str, object]:
        """Read only an authenticated receipt; NEVER replay physical movement."""
        expected_plan = _encode(_plan_body(plan, self.session_id))
        with self._lock:
            row = self._connection.execute(
                "SELECT session_id, inventory_digest, plan_payload,"
                " plan_mac, state, receipt_payload, receipt_mac FROM "
                + TABLE + " WHERE plan_digest = ?",
                (plan.digest,),
            ).fetchone()
            if (
                row is None
                or row[0] != self.session_id
                or row[1] != plan.inventory_digest
                or row[2] != expected_plan
                or type(row[3]) is not str
                or not hmac.compare_digest(
                    _hex(row[3], "plan MAC"),
                    _sign(self._key, _plan_body(plan, self.session_id)),
                )
                or row[4] != "committed"
                or type(row[5]) is not bytes
                or type(row[6]) is not str
            ):
                raise KVMigrationOutcomeUnknown(
                    "no authenticated committed migration receipt"
                )
            try:
                receipt = json.loads(row[5])
                if not hmac.compare_digest(
                    _hex(row[6], "receipt MAC"), _sign(self._key, receipt)
                ):
                    raise ValueError("receipt authentication failed")
                if receipt["plan_digest"] != plan.digest:
                    raise ValueError("receipt plan mismatch")
                if len(row[5]) > MAX_RECEIPT_BYTES:
                    raise ValueError("receipt byte budget exceeded")
                return receipt
            except (TypeError, ValueError, KeyError) as exc:
                raise KVMigrationOutcomeUnknown(
                    "committed migration receipt corrupted"
                ) from exc


class KVJournaledTierController:
    """Application seam: write intent, migrate ONCE, then commit receipt."""

    def __init__(self, controller: KVLiveTierController, journal: KVMigrationJournal):
        if not isinstance(controller, KVLiveTierController):
            raise ValueError("canonical live KV controller required")
        if not isinstance(journal, KVMigrationJournal):
            raise ValueError("canonical migration journal required")
        self._controller = controller
        self._journal = journal
        self._lock = RLock()

    def plan_live(self):
        return self._controller.plan_live()

    def apply_once(self, plan: TierPlan) -> TierApplyReceipt:
        with self._lock:
            self._journal.begin(plan)
            try:
                receipt = self._controller.apply_live(plan)
                self._journal.commit(plan, receipt)
                return receipt
            except BaseException as exc:
                # The adapter may already have moved a subset of pages.
                # A RUNNING journal row fences any future automatic retry.
                raise KVMigrationOutcomeUnknown(
                    "KV migration outcome uncertain; operator reconciliation required"
                ) from exc


__all__ = [
    "KVMigrationJournal", "KVJournaledTierController",
    "KVMigrationOutcomeUnknown",
]
