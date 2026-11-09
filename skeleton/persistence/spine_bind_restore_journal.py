"""Append-only journal for anchored P2 bind restore receipts.

The journal is evidence only. It preserves every accepted receipt, links rows
per tenant, rejects digest rewrites, and keeps all activation-bearing fields
dark.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


class SpineBindRestoreJournalError(RuntimeError):
    """Restore journal rejected its input. Not a maturity signal."""


_ZERO = "0" * 64


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SpineBindRestoreJournalError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


def _hex64(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise SpineBindRestoreJournalError(f"{field} must be lowercase SHA-256 hex")
    return value


def _receipt_digest(receipt: dict[str, Any]) -> str:
    expected = _hex64(receipt.get("digest"), "receipt.digest")
    actual = hashlib.sha256(
        json.dumps(
            {key: value for key, value in receipt.items() if key != "digest"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if actual != expected:
        raise SpineBindRestoreJournalError("restore receipt digest mismatch")
    return expected


class SpineBindRestoreJournal:
    """Append immutable receipt rows and link each tenant's history."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_bind_restore_receipt (
                journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                receipt_digest TEXT NOT NULL,
                previous_digest TEXT NOT NULL,
                row_digest TEXT NOT NULL,
                backup_restore_digest TEXT NOT NULL,
                recovery_digest TEXT NOT NULL,
                chain_digest TEXT NOT NULL,
                bundle_digest TEXT NOT NULL,
                checkpoint_rows INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                activated INTEGER NOT NULL,
                apply_landed INTEGER NOT NULL,
                live_motor INTEGER NOT NULL,
                dispatcher_running INTEGER NOT NULL,
                ci_green INTEGER NOT NULL,
                merged INTEGER NOT NULL,
                UNIQUE(tenant_id, receipt_digest)
            )
            """
        )
        self._connection.commit()

    def append(
        self,
        receipt: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("kind") != "spine_bind_restore_receipt":
            raise SpineBindRestoreJournalError("receipt must be a spine_bind_restore_receipt")
        tenant_id = receipt.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindRestoreJournalError("receipt tenant missing")
        if receipt.get("restored") is not True or receipt.get("verified") is not True:
            raise SpineBindRestoreJournalError("receipt is not verified")
        for flag in (
            "activated",
            "apply_landed",
            "live_motor",
            "dispatcher_running",
            "provider_surface_green",
            "pr_automation_green",
            "ci_green",
            "merged",
        ):
            if receipt.get(flag) is not False:
                raise SpineBindRestoreJournalError("restore receipt is not dark")

        receipt_digest = _receipt_digest(receipt)
        backup = _hex64(receipt.get("backup_restore_digest"), "backup_restore_digest")
        recovery = _hex64(receipt.get("recovery_digest"), "recovery_digest")
        chain = _hex64(receipt.get("chain_digest"), "chain_digest")
        bundle = _hex64(receipt.get("bundle_digest"), "bundle_digest")
        checkpoint_rows = receipt.get("checkpoint_rows")
        if isinstance(checkpoint_rows, bool) or not isinstance(checkpoint_rows, int) or checkpoint_rows < 1:
            raise SpineBindRestoreJournalError("checkpoint_rows must be a positive integer")
        instant = _aware(now or datetime.now(timezone.utc))

        existing = self._connection.execute(
            """
            SELECT journal_id, previous_digest, row_digest, recorded_at
            FROM spine_bind_restore_receipt
            WHERE tenant_id = ? AND receipt_digest = ?
            """,
            (tenant_id, receipt_digest),
        ).fetchone()
        if existing is not None:
            return self._card(
                tenant_id=tenant_id,
                receipt_digest=receipt_digest,
                previous_digest=existing["previous_digest"],
                row_digest=existing["row_digest"],
                journal_id=int(existing["journal_id"]),
                recorded_at=existing["recorded_at"],
                inserted=False,
            )

        previous = self._connection.execute(
            """
            SELECT receipt_digest
            FROM spine_bind_restore_receipt
            WHERE tenant_id = ?
            ORDER BY journal_id DESC
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
        previous_digest = _ZERO if previous is None else str(previous["receipt_digest"])
        recorded_at = instant.isoformat()
        row_digest = hashlib.sha256(
            "|".join(
                (
                    previous_digest,
                    tenant_id,
                    receipt_digest,
                    backup,
                    recovery,
                    chain,
                    bundle,
                    str(checkpoint_rows),
                    recorded_at,
                )
            ).encode("utf-8")
        ).hexdigest()
        cursor = self._connection.execute(
            """
            INSERT INTO spine_bind_restore_receipt (
                tenant_id, receipt_digest, previous_digest, row_digest,
                backup_restore_digest, recovery_digest, chain_digest,
                bundle_digest, checkpoint_rows, recorded_at, activated,
                apply_landed, live_motor, dispatcher_running, ci_green, merged
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0)
            """,
            (
                tenant_id,
                receipt_digest,
                previous_digest,
                row_digest,
                backup,
                recovery,
                chain,
                bundle,
                checkpoint_rows,
                recorded_at,
            ),
        )
        self._connection.commit()
        return self._card(
            tenant_id=tenant_id,
            receipt_digest=receipt_digest,
            previous_digest=previous_digest,
            row_digest=row_digest,
            journal_id=int(cursor.lastrowid),
            recorded_at=recorded_at,
            inserted=True,
        )

    @staticmethod
    def _card(
        *,
        tenant_id: str,
        receipt_digest: str,
        previous_digest: str,
        row_digest: str,
        journal_id: int,
        recorded_at: str,
        inserted: bool,
    ) -> dict[str, Any]:
        return {
            "kind": "spine_bind_restore_journal",
            "hit": True,
            "law": "restore-journal-is-append-only",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "receipt_digest": receipt_digest,
            "previous_digest": previous_digest,
            "row_digest": row_digest,
            "journal_id": journal_id,
            "recorded_at": recorded_at,
            "inserted": inserted,
            "rewritten": False,
            "activated": False,
            "apply_landed": False,
            "live_motor": False,
            "dispatcher_running": False,
            "ci_green": False,
            "merged": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def count(self, tenant_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM spine_bind_restore_receipt WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
