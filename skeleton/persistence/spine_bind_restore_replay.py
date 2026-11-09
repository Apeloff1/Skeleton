"""Replay verification for the anchored restore-receipt journal."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


class SpineBindRestoreReplayError(RuntimeError):
    """Restore replay rejected its input. Not a maturity signal."""


class SpineBindRestoreReplay:
    """Prove a receipt replay does not insert, rewrite, or activate."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def replay(self, journal: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(journal, dict) or journal.get("kind") != "spine_bind_restore_journal":
            raise SpineBindRestoreReplayError("journal must be a spine_bind_restore_journal")
        tenant_id = journal.get("tenant_id")
        receipt_digest = journal.get("receipt_digest")
        row_digest = journal.get("row_digest")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindRestoreReplayError("journal tenant missing")
        if not isinstance(receipt_digest, str) or len(receipt_digest) != 64:
            raise SpineBindRestoreReplayError("receipt digest missing")
        if not isinstance(row_digest, str) or len(row_digest) != 64:
            raise SpineBindRestoreReplayError("row digest missing")
        if journal.get("activated") is not False:
            raise SpineBindRestoreReplayError("journal is activated")

        before = self._count(tenant_id)
        try:
            row = self._connection.execute(
                """
                SELECT row_digest, activated, apply_landed, live_motor,
                       dispatcher_running, ci_green, merged
                FROM spine_bind_restore_receipt
                WHERE tenant_id = ? AND receipt_digest = ?
                """,
                (tenant_id, receipt_digest),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindRestoreReplayError("restore journal missing") from exc
        if row is None:
            raise SpineBindRestoreReplayError("restore journal row missing")
        if row["row_digest"] != row_digest:
            raise SpineBindRestoreReplayError("restore journal row digest mismatch")
        for flag in ("activated", "apply_landed", "live_motor", "dispatcher_running", "ci_green", "merged"):
            if int(row[flag]) != 0:
                raise SpineBindRestoreReplayError("restore journal row is not dark")
        after = self._count(tenant_id)
        if before != after:
            raise SpineBindRestoreReplayError("restore replay inserted a row")
        return {
            "kind": "spine_bind_restore_replay",
            "hit": True,
            "law": "restore-replay-does-not-insert",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "receipt_digest": receipt_digest,
            "row_digest": row_digest,
            "rows_before": before,
            "rows_after": after,
            "inserted": False,
            "rewritten": False,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _count(self, tenant_id: str) -> int:
        try:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n FROM spine_bind_restore_receipt WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindRestoreReplayError("restore journal missing") from exc
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
