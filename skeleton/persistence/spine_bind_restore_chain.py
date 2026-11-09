"""Hash-chain verifier for anchored restore-receipt journal rows."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from typing import Any


class SpineBindRestoreChainError(RuntimeError):
    """Restore chain rejected its input. Not a maturity signal."""


_ZERO = "0" * 64


class SpineBindRestoreChain:
    """Recompute tenant receipt continuity and fail closed on mutation."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def seal(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindRestoreChainError("tenant_id must be non-empty text")
        try:
            rows = self._connection.execute(
                """
                SELECT journal_id, tenant_id, receipt_digest, previous_digest,
                       row_digest, backup_restore_digest, recovery_digest,
                       chain_digest, bundle_digest, checkpoint_rows, recorded_at,
                       activated, apply_landed, live_motor, dispatcher_running,
                       ci_green, merged
                FROM spine_bind_restore_receipt
                WHERE tenant_id = ?
                ORDER BY journal_id
                """,
                (tenant_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SpineBindRestoreChainError("restore journal missing") from exc
        if not rows:
            raise SpineBindRestoreChainError("restore journal empty")

        previous = _ZERO
        aggregate = _ZERO
        for row in rows:
            if row["tenant_id"] != tenant_id:
                raise SpineBindRestoreChainError("foreign restore row leaked")
            if row["previous_digest"] != previous:
                raise SpineBindRestoreChainError("restore receipt continuity broke")
            for flag in ("activated", "apply_landed", "live_motor", "dispatcher_running", "ci_green", "merged"):
                if int(row[flag]) != 0:
                    raise SpineBindRestoreChainError("restore journal row is not dark")
            expected_row = hashlib.sha256(
                "|".join(
                    (
                        str(row["previous_digest"]),
                        str(row["tenant_id"]),
                        str(row["receipt_digest"]),
                        str(row["backup_restore_digest"]),
                        str(row["recovery_digest"]),
                        str(row["chain_digest"]),
                        str(row["bundle_digest"]),
                        str(row["checkpoint_rows"]),
                        str(row["recorded_at"]),
                    )
                ).encode("utf-8")
            ).hexdigest()
            if expected_row != row["row_digest"]:
                raise SpineBindRestoreChainError("restore row digest mismatch")
            aggregate = hashlib.sha256(
                f"{aggregate}|{row['row_digest']}".encode("utf-8")
            ).hexdigest()
            previous = str(row["receipt_digest"])

        return {
            "kind": "spine_bind_restore_chain",
            "hit": True,
            "law": "restore-journal-hash-chain",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "rows": len(rows),
            "head_receipt_digest": previous,
            "digest": aggregate,
            "rewritten": False,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
