"""Append-only durable evidence for a refused bind seal.

The durable row carries enough fixed evidence to reconstruct its SHA-256 digest
without trusting the original in-memory card. A second identity-changing write
fails closed. The journal grants no apply or merge authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


class SpineBindHoldJournalError(RuntimeError):
    """Bind hold journal rejected its inputs. Not a maturity signal."""


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _bind_hold_refusal_digest(
    *,
    tenant_id: str,
    outbox_id: str,
    hold_id: int,
    hold_reason: str,
    bind_digest: str,
    epoch: int,
) -> str:
    evidence = {
        "tenant_id": tenant_id,
        "outbox_id": outbox_id,
        "hold_id": hold_id,
        "hold_reason": hold_reason,
        "bind_digest": bind_digest,
        "epoch": epoch,
        "held": True,
        "sealed": False,
        "moved": False,
        "applied": 0,
        "apply_landed": False,
    }
    encoded = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineBindHoldJournal:
    """Seal a refusal into reconstructable durable evidence. Do not rewrite it."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(
            str(journal_path),
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        table = self._connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'spine_bind_hold'
            """
        ).fetchone()
        if table is None:
            self._create_current_table()
            self._connection.commit()
            return

        columns = {
            str(row["name"])
            for row in self._connection.execute(
                "PRAGMA table_info(spine_bind_hold)"
            )
        }
        if "hold_id" not in columns:
            self._connection.execute(
                """
                ALTER TABLE spine_bind_hold
                ADD COLUMN hold_id INTEGER NOT NULL DEFAULT 0
                """
            )
        if "hold_reason" not in columns:
            self._connection.execute(
                """
                ALTER TABLE spine_bind_hold
                ADD COLUMN hold_reason TEXT NOT NULL DEFAULT ''
                """
            )
        if "bind_digest" not in columns:
            self._connection.execute(
                """
                ALTER TABLE spine_bind_hold
                ADD COLUMN bind_digest TEXT NOT NULL DEFAULT ''
                """
            )
        self._connection.commit()

        columns = {
            str(row["name"])
            for row in self._connection.execute(
                "PRAGMA table_info(spine_bind_hold)"
            )
        }
        if "refusal_id" in columns:
            return

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute(
                "ALTER TABLE spine_bind_hold RENAME TO spine_bind_hold_legacy"
            )
            self._create_current_table()
            self._connection.execute(
                """
                INSERT INTO spine_bind_hold(
                    tenant_id, outbox_id, hold_id, hold_reason,
                    bind_digest, digest, held, applied, epoch
                )
                SELECT tenant_id, outbox_id, hold_id, hold_reason,
                       bind_digest, digest, held, applied, epoch
                FROM spine_bind_hold_legacy
                ORDER BY rowid
                """
            )
            self._connection.execute("DROP TABLE spine_bind_hold_legacy")
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def _create_current_table(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE spine_bind_hold (
                refusal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                hold_id INTEGER NOT NULL DEFAULT 0,
                hold_reason TEXT NOT NULL DEFAULT '',
                bind_digest TEXT NOT NULL DEFAULT '',
                digest TEXT NOT NULL,
                held INTEGER NOT NULL,
                applied INTEGER NOT NULL,
                epoch INTEGER NOT NULL,
                UNIQUE(
                    tenant_id,
                    outbox_id,
                    hold_id,
                    bind_digest,
                    epoch
                )
            )
            """
        )

    def append(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_hold":
            raise SpineBindHoldJournalError("card must be a spine_bind_hold")
        if (
            card.get("law") != "held-id-refuses-bind"
            or card.get("citation") != "VOL-134"
        ):
            raise SpineBindHoldJournalError("refusal authority identity changed")
        if card.get("held") is not True or card.get("sealed") is not False:
            raise SpineBindHoldJournalError("refusal is not a hold")
        if (
            card.get("applied") != 0
            or card.get("moved") is not False
            or card.get("apply_landed") is not False
        ):
            raise SpineBindHoldJournalError("refusal is not dark")
        if card.get("stored_prose") != 0:
            raise SpineBindHoldJournalError("refusal stored prose changed")
        for field in (
            "completion_checkbox",
            "implementation_signature",
            "verification_signature",
        ):
            if card.get(field) is not False:
                raise SpineBindHoldJournalError(
                    f"refusal overclaimed authority: {field}"
                )

        tenant_id = card.get("tenant_id")
        outbox_id = card.get("outbox_id")
        hold_reason = card.get("reason")
        bind_digest = card.get("bind_digest")
        hold_id = card.get("hold_id")
        epoch = card.get("epoch_before")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldJournalError("tenant_id must be non-empty text")
        if not isinstance(outbox_id, str) or not outbox_id.strip():
            raise SpineBindHoldJournalError("outbox_id must be non-empty text")
        if not isinstance(hold_reason, str) or not hold_reason.strip():
            raise SpineBindHoldJournalError("hold reason must be non-empty text")
        if (
            not isinstance(bind_digest, str)
            or _DIGEST_RE.fullmatch(bind_digest) is None
        ):
            raise SpineBindHoldJournalError("bind digest is invalid")
        if (
            isinstance(hold_id, bool)
            or not isinstance(hold_id, int)
            or hold_id < 1
        ):
            raise SpineBindHoldJournalError("hold_id is invalid")
        if (
            isinstance(epoch, bool)
            or not isinstance(epoch, int)
            or epoch < 0
            or epoch != card.get("epoch_after")
        ):
            raise SpineBindHoldJournalError("refusal epoch moved")

        digest = _bind_hold_refusal_digest(
            tenant_id=tenant_id,
            outbox_id=outbox_id,
            hold_id=hold_id,
            hold_reason=hold_reason,
            bind_digest=bind_digest,
            epoch=epoch,
        )
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self._connection.execute(
                """
                SELECT refusal_id, hold_reason, digest, held, applied
                FROM spine_bind_hold
                WHERE tenant_id = ?
                  AND outbox_id = ?
                  AND hold_id = ?
                  AND bind_digest = ?
                  AND epoch = ?
                """,
                (
                    tenant_id,
                    outbox_id,
                    hold_id,
                    bind_digest,
                    epoch,
                ),
            ).fetchone()
            if existing is not None:
                durable = {
                    "hold_reason": str(existing["hold_reason"]),
                    "digest": str(existing["digest"]),
                    "held": int(existing["held"]),
                    "applied": int(existing["applied"]),
                }
                expected = {
                    "hold_reason": hold_reason,
                    "digest": digest,
                    "held": 1,
                    "applied": 0,
                }
                if durable != expected:
                    raise SpineBindHoldJournalError(
                        "bind hold journal rewrite"
                    )
                refusal_id = int(existing["refusal_id"])
            else:
                cursor = self._connection.execute(
                    """
                    INSERT INTO spine_bind_hold (
                        tenant_id, outbox_id, hold_id, hold_reason,
                        bind_digest, digest, held, applied, epoch
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)
                    """,
                    (
                        tenant_id,
                        outbox_id,
                        hold_id,
                        hold_reason,
                        bind_digest,
                        digest,
                        epoch,
                    ),
                )
                refusal_id = int(cursor.lastrowid)
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

        return {
            "kind": "spine_bind_hold_journal",
            "hit": True,
            "law": "bind-hold-not-rewritten",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "outbox_id": outbox_id,
            "refusal_id": refusal_id,
            "hold_id": hold_id,
            "hold_reason": hold_reason,
            "bind_digest": bind_digest,
            "digest": digest,
            "rewritten": False,
            "applied": 0,
            "sealed": False,
            "epoch": epoch,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()


__all__ = [
    "SpineBindHoldJournal",
    "SpineBindHoldJournalError",
]
