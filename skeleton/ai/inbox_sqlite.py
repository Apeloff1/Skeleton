"""Durable SQLite adapter for the canonical AI InboxLedger receipt contract.

This persists deduplication, producer epochs, monotonic sequence floors and
quarantine receipts across restarts. It deliberately does NOT execute external
effects, authorize tools, or claim exactly-once effects across databases.
External effect receipts must be created by their canonical durable authority.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading

from .inbox_causality import (
    InboundMessage, ProcessingReceipt, QuarantineReceipt,
    processing_receipt, quarantine_receipt,
)

MAX_CAUSES = 64
MAX_EFFECTS = 64
MAX_TEXT_LENGTH = 512


def _text(value: object, label: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= MAX_TEXT_LENGTH:
        raise ValueError(f"invalid {label}")
    if value != value.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError(f"invalid {label}")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError(f"invalid {label}") from exc
    return value


def _number(value: object, label: str, *, lower: int = 0) -> int:
    if type(value) is not int or not lower <= value <= 2**63 - 1:
        raise ValueError(f"invalid {label}")
    return value


def _message(message: InboundMessage) -> InboundMessage:
    if not isinstance(message, InboundMessage):
        raise TypeError("InboundMessage required")
    _text(message.producer_id, "producer_id")
    _text(message.payload_digest, "payload_digest")
    _number(message.producer_epoch, "producer_epoch")
    _number(message.sequence, "sequence")
    if type(message.causal_ids) is not tuple or len(message.causal_ids) > MAX_CAUSES:
        raise ValueError("causal IDs outside budget")
    for key in message.causal_ids:
        _text(key, "causal id")
    canonical = InboundMessage.create(
        message.producer_id, message.producer_epoch,
        message.sequence, message.payload_digest, message.causal_ids,
    )
    if canonical != message:
        raise ValueError("inbound message identity is noncanonical")
    return message


def _effects(effect_record_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if type(effect_record_ids) not in (tuple, list) or len(effect_record_ids) > MAX_EFFECTS:
        raise ValueError("effect receipt count exceeds budget")
    items = tuple(_text(key, "effect receipt") for key in effect_record_ids)
    if len(items) != len(set(items)):
        raise ValueError("duplicate effect receipts")
    return tuple(sorted(items))


def _json_array(raw: str, label: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"persisted {label} is invalid JSON") from exc
    if type(parsed) is not list:
        raise ValueError(f"persisted {label} must be an array")
    return tuple(parsed)


class SQLiteInboxLedger:
    """Single canonical processed-message ledger with transactional durability.

    A write receipt is *evidence of a separately committed effect*, not an
    authorization to perform that effect. Consumers must commit effects and
    ledger state in one transaction when both share a database, or use the
    existing outbox/inbox/compensation protocol for cross-store operations.
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        replay_window: int = 1024,
        max_receipts: int = 100_000,
        require_causal_receipts: bool = True,
    ) -> None:
        self.replay_window = _number(replay_window, "replay_window", lower=1)
        self.max_receipts = _number(max_receipts, "max_receipts", lower=1)
        if self.replay_window > 1_000_000 or self.max_receipts > 1_000_000:
            raise ValueError("inbox budgets exceed configured architecture maximum")
        if type(require_causal_receipts) is not bool:
            raise ValueError("require_causal_receipts must be boolean")
        self.require_causal_receipts = require_causal_receipts
        if type(path) not in (str, Path):
            raise ValueError("SQLite inbox path must be a string or Path")
        if str(path) != ":memory:":
            target = Path(path)
            if target.is_symlink() or target.parent.is_symlink() or not target.parent.is_dir():
                raise ValueError("SQLite inbox path requires a preprovisioned safe parent")
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            str(path), isolation_level=None, check_same_thread=False, timeout=5.0,
        )
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                PRAGMA busy_timeout=5000;

                CREATE TABLE IF NOT EXISTS ai_inbox_config(
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    replay_window INTEGER NOT NULL,
                    max_receipts INTEGER NOT NULL,
                    require_causal_receipts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_inbox_producer(
                    producer_id TEXT PRIMARY KEY,
                    producer_epoch INTEGER NOT NULL,
                    highest_sequence INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_inbox_processed(
                    message_id TEXT PRIMARY KEY,
                    producer_id TEXT NOT NULL,
                    producer_epoch INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    payload_digest TEXT NOT NULL,
                    causal_json TEXT NOT NULL,
                    write_receipt_id TEXT NOT NULL,
                    effect_json TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    UNIQUE(producer_id, producer_epoch, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_ai_inbox_processed_producer
                ON ai_inbox_processed(producer_id, producer_epoch, sequence);
                CREATE TABLE IF NOT EXISTS ai_inbox_quarantine(
                    message_id TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    receipt_id TEXT NOT NULL
                );
                """
            )
            config = self._db.execute("SELECT * FROM ai_inbox_config WHERE id=1").fetchone()
            expected = (
                self.replay_window, self.max_receipts,
                int(self.require_causal_receipts),
            )
            if config is None:
                self._db.execute(
                    "INSERT INTO ai_inbox_config VALUES (1, ?, ?, ?)", expected,
                )
            elif tuple(config[field] for field in (
                "replay_window", "max_receipts", "require_causal_receipts",
            )) != expected:
                self._db.close()
                raise ValueError(
                    "persisted inbox policy mismatch; explicit migration required"
                )

    @staticmethod
    def _receipt(row: sqlite3.Row) -> ProcessingReceipt:
        effect_ids = _effects(_json_array(row["effect_json"], "effect identities"))
        causes = _json_array(row["causal_json"], "causal identities")
        message = InboundMessage.create(
            row["producer_id"], _number(row["producer_epoch"], "stored epoch"),
            _number(row["sequence"], "stored sequence"),
            row["payload_digest"], causes,
        )
        if message.message_id != row["message_id"]:
            raise ValueError("persisted inbound identity mismatch")
        receipt = processing_receipt(message, row["write_receipt_id"], effect_ids)
        if receipt.receipt_id != row["receipt_id"]:
            raise ValueError("persisted processing receipt digest mismatch")
        return receipt

    def _existing(self, message_id: str) -> ProcessingReceipt | None:
        row = self._db.execute(
            "SELECT * FROM ai_inbox_processed WHERE message_id=?", (message_id,),
        ).fetchone()
        return self._receipt(row) if row is not None else None

    def _check_pending(self, message: InboundMessage) -> None:
        state = self._db.execute(
            "SELECT producer_epoch, highest_sequence FROM ai_inbox_producer "
            "WHERE producer_id=?", (message.producer_id,),
        ).fetchone()
        if state is None:
            highest = -1
        else:
            prior_epoch = _number(state["producer_epoch"], "stored epoch")
            prior_highest = _number(state["highest_sequence"], "stored highwater", lower=-1)
            if message.producer_epoch < prior_epoch:
                raise PermissionError("stale producer epoch")
            highest = -1 if message.producer_epoch > prior_epoch else prior_highest
        if message.sequence <= highest - self.replay_window:
            raise PermissionError("message outside replay window")
        if message.sequence > highest + 1:
            raise PermissionError("producer sequence gap")
        if message.sequence <= highest:
            raise PermissionError("sequence already processed by a different identity")
        if self.require_causal_receipts:
            for cause_id in message.causal_ids:
                if self._existing(cause_id) is None:
                    raise PermissionError("causal predecessor not committed")

    def admit(self, message: InboundMessage) -> ProcessingReceipt | None:
        message = _message(message)
        with self._lock:
            prior = self._existing(message.message_id)
            if prior is not None:
                return prior
            self._check_pending(message)
            return None

    def commit(
        self, message: InboundMessage, write_receipt_id: str,
        effect_record_ids: tuple[str, ...] | list[str] = (),
    ) -> ProcessingReceipt:
        message = _message(message)
        write_receipt_id = _text(write_receipt_id, "write receipt")
        effect_ids = _effects(effect_record_ids)
        proposal = processing_receipt(message, write_receipt_id, effect_ids)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                previous = self._existing(message.message_id)
                if previous is not None:
                    if previous != proposal:
                        raise PermissionError("duplicate message changed processing effect")
                    self._db.execute("COMMIT")
                    return previous
                self._check_pending(message)
                count = self._db.execute(
                    "SELECT COUNT(*) FROM ai_inbox_processed",
                ).fetchone()[0]
                if count >= self.max_receipts:
                    raise PermissionError("durable inbox receipt capacity exhausted")
                self._db.execute(
                    """
                    INSERT INTO ai_inbox_processed(
                        message_id, producer_id, producer_epoch, sequence,
                        payload_digest, causal_json, write_receipt_id,
                        effect_json, receipt_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.message_id, message.producer_id,
                        message.producer_epoch, message.sequence,
                        message.payload_digest,
                        json.dumps(message.causal_ids),
                        write_receipt_id, json.dumps(effect_ids),
                        proposal.receipt_id,
                    ),
                )
                self._db.execute(
                    """
                    INSERT INTO ai_inbox_producer(
                        producer_id, producer_epoch, highest_sequence
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(producer_id) DO UPDATE SET
                        producer_epoch=excluded.producer_epoch,
                        highest_sequence=excluded.highest_sequence
                    """,
                    (
                        message.producer_id, message.producer_epoch,
                        message.sequence,
                    ),
                )
                self._db.execute("COMMIT")
                return proposal
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def quarantine(
        self, message: InboundMessage, reason: str, evidence_id: str,
    ) -> QuarantineReceipt:
        message = _message(message)
        result = quarantine_receipt(
            message, _text(reason, "quarantine reason"),
            _text(evidence_id, "quarantine evidence"),
        )
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT * FROM ai_inbox_quarantine WHERE message_id=?",
                    (message.message_id,),
                ).fetchone()
                if row is not None:
                    if (row["reason"] != result.reason or
                            row["evidence_id"] != result.evidence_id or
                            row["receipt_id"] != result.receipt_id):
                        raise PermissionError("quarantine evidence changed")
                else:
                    count = self._db.execute(
                        "SELECT COUNT(*) FROM ai_inbox_quarantine",
                    ).fetchone()[0]
                    if count >= self.max_receipts:
                        raise PermissionError("durable inbox quarantine capacity exhausted")
                    self._db.execute(
                        "INSERT INTO ai_inbox_quarantine VALUES (?, ?, ?, ?)",
                        (
                            message.message_id, result.reason,
                            result.evidence_id, result.receipt_id,
                        ),
                    )
                self._db.execute("COMMIT")
                return result
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "SQLiteInboxLedger":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


__all__ = ["SQLiteInboxLedger"]
