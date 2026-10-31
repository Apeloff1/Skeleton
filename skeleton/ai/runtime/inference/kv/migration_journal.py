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

    def verified_inventory(self) -> dict[str, int | str]:
        """Authenticate ALL bounded historical rows before new physical work.

        A signed committed receipt is not proof that a backend is presently
        resident in the claimed tier. This read-only integrity check merely
        prevents new work from silently proceeding past forged/corrupted
        journal history. RUNNING intents remain unresolved, never replayed.
        """
        with self._lock:
            try:
                rows = self._connection.execute(
                    "SELECT plan_digest, session_id, inventory_digest,"
                    " plan_payload, plan_mac, state, receipt_payload, receipt_mac"
                    " FROM " + TABLE
                ).fetchall()
                if len(rows) > MAX_ROWS:
                    raise ValueError("unbounded migration journal")
                running = 0
                committed = 0
                for (
                    plan_digest, session_id, inventory_digest, payload,
                    plan_mac, state, receipt_payload, receipt_mac,
                ) in rows:
                    _hex(plan_digest, "stored plan digest")
                    _hex(inventory_digest, "stored inventory digest")
                    if session_id != self.session_id:
                        raise ValueError("foreign migration session")
                    if type(payload) is not bytes or len(payload) > MAX_RECEIPT_BYTES:
                        raise ValueError("unbounded stored migration plan")
                    plan = json.loads(payload)
                    if (
                        type(plan) is not dict
                        or set(plan) != {
                            "schema", "session_id", "plan_digest",
                            "inventory_digest", "moves",
                        }
                        or plan["schema"] != SCHEMA
                        or plan["session_id"] != session_id
                        or plan["plan_digest"] != plan_digest
                        or plan["inventory_digest"] != inventory_digest
                        or type(plan["moves"]) is not list
                        or len(plan["moves"]) > MAX_MOVES
                        or _encode(plan) != payload
                        or type(plan_mac) is not str
                        or not hmac.compare_digest(
                            _hex(plan_mac, "stored plan MAC"),
                            _sign(self._key, plan),
                        )
                    ):
                        raise ValueError("untrusted historical migration plan")
                    moves = plan["moves"]
                    if any(
                        type(move) is not dict
                        or set(move) != {"page_key", "source", "target", "bytes"}
                        or type(move["page_key"]) is not str
                        or not move["page_key"]
                        or type(move["source"]) is not str
                        or type(move["target"]) is not str
                        or type(move["bytes"]) is not int
                        or move["bytes"] <= 0
                        for move in moves
                    ):
                        raise ValueError("invalid historical page move")
                    keys = [move["page_key"] for move in moves]
                    if len(set(keys)) != len(keys):
                        raise ValueError("duplicate historical page identity")
                    if state == "running":
                        if receipt_payload is not None or receipt_mac is not None:
                            raise ValueError("uncommitted migration has a receipt")
                        running += 1
                    elif state == "committed":
                        if (
                            type(receipt_payload) is not bytes
                            or len(receipt_payload) > MAX_RECEIPT_BYTES
                            or type(receipt_mac) is not str
                        ):
                            raise ValueError("missing committed migration receipt")
                        receipt = json.loads(receipt_payload)
                        if (
                            type(receipt) is not dict
                            or set(receipt) != {
                                "schema", "plan_digest", "moved", "rejected",
                            }
                            or receipt["schema"] != "skeleton.ai.kv-pressure-apply.v1"
                            or receipt["plan_digest"] != plan_digest
                            or type(receipt["moved"]) is not list
                            or type(receipt["rejected"]) is not list
                            or _encode(receipt) != receipt_payload
                            or not hmac.compare_digest(
                                _hex(receipt_mac, "stored receipt MAC"),
                                _sign(self._key, receipt),
                            )
                        ):
                            raise ValueError("untrusted historical migration receipt")
                        moved = receipt["moved"]
                        rejected = receipt["rejected"]
                        if (
                            any(type(key) is not str for key in moved)
                            or any(type(item) is not list or len(item) != 2
                                   or type(item[0]) is not str
                                   or type(item[1]) is not str
                                   or not 1 <= len(item[1]) <= 128
                                   for item in rejected)
                            or len(set(moved + [item[0] for item in rejected]))
                                != len(moved) + len(rejected)
                            or set(moved + [item[0] for item in rejected]) != set(keys)
                        ):
                            raise ValueError("historical migration accounting mismatch")
                        committed += 1
                    else:
                        raise ValueError("invalid historical migration state")
                return {
                    "schema": "skeleton.ai.kv-migration-inventory.v1",
                    "rows": len(rows), "running": running,
                    "committed": committed,
                }
            except (sqlite3.Error, ValueError, TypeError, KeyError,
                    OverflowError, RecursionError) as exc:
                raise KVMigrationOutcomeUnknown(
                    "migration journal history unverifiable"
                ) from exc

    def begin(self, plan: TierPlan) -> None:
        """Commit intent before touching the physical KV storage adapter."""
        body = _plan_body(plan, self.session_id)
        payload = _encode(body)
        mac = _sign(self._key, body)
        with self._lock:
            self._begin()
            try:
                inventory = self.verified_inventory()
                if inventory["running"]:

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
                if len(row[5]) > MAX_RECEIPT_BYTES:
                    raise ValueError("receipt byte budget exceeded")
                receipt = json.loads(row[5])
                if type(receipt) is not dict or set(receipt) != {
                    "schema", "plan_digest", "moved", "rejected",
                }:
                    raise ValueError("invalid committed receipt shape")
                if _encode(receipt) != row[5]:
                    raise ValueError("noncanonical committed receipt")
                if not hmac.compare_digest(
                    _hex(row[6], "receipt MAC"), _sign(self._key, receipt)
                ):
                    raise ValueError("receipt authentication failed")
                if (
                    receipt["schema"] != "skeleton.ai.kv-pressure-apply.v1"
                    or receipt["plan_digest"] != plan.digest
                    or type(receipt["moved"]) is not list
                    or type(receipt["rejected"]) is not list
                    or any(type(key) is not str for key in receipt["moved"])
                    or any(
                        type(item) is not list or len(item) != 2
                        or any(type(value) is not str for value in item)
                        for item in receipt["rejected"]
                    )
                ):
                    raise ValueError("invalid committed migration accounting")
                canonical = TierApplyReceipt(
                    plan.digest, tuple(receipt["moved"]),
                    tuple(tuple(item) for item in receipt["rejected"]),
                    sha256(_encode(receipt)).hexdigest(),
                )
                if _receipt_body(plan, canonical) != receipt:
                    raise ValueError("committed migration accounting mismatch")
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
                if receipt.rejected:
                    # A storage adapter can move a page and then raise.
                    # A "rejected" per-page result is NOT proof that no
                    # physical side effect occurred. Leave the RUNNING
                    # intent unresolved and fence all subsequent moves.
                    raise KVMigrationOutcomeUnknown(
                        "partial or rejected KV movement requires operator reconciliation"
                    )
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
