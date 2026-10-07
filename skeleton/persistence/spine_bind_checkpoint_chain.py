"""Hash-chain verification for bind recovery checkpoints."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from typing import Any


class SpineBindCheckpointChainError(RuntimeError):
    """Checkpoint chain rejected its inputs. Not a maturity signal."""


_COLUMNS = (
    "tenant_id",
    "recovery_digest",
    "snapshot_digest",
    "sealed_at",
    "activated",
    "apply_landed",
    "live_motor",
    "dispatcher_running",
    "ci_green",
    "merged",
)


class SpineBindCheckpointChain:
    """Seal checkpoint rows into a deterministic SHA-256 chain."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def seal(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindCheckpointChainError("tenant_id must be non-empty text")
        try:
            rows = self._connection.execute(
                """
                SELECT tenant_id, recovery_digest, snapshot_digest, sealed_at,
                       activated, apply_landed, live_motor, dispatcher_running,
                       ci_green, merged
                FROM spine_bind_checkpoint
                WHERE tenant_id = ?
                ORDER BY sealed_at, recovery_digest
                """,
                (tenant_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SpineBindCheckpointChainError("checkpoint journal missing") from exc
        if not rows:
            raise SpineBindCheckpointChainError("checkpoint journal empty")

        digest = "0" * 64
        for row in rows:
            for flag in _COLUMNS[4:]:
                if int(row[flag]) != 0:
                    raise SpineBindCheckpointChainError("checkpoint row is not dark")
            payload = "|".join(str(row[name]) for name in _COLUMNS)
            digest = hashlib.sha256(f"{digest}|{payload}".encode("utf-8")).hexdigest()
        return {
            "kind": "spine_bind_checkpoint_chain",
            "hit": True,
            "law": "checkpoint-hash-chain",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "rows": len(rows),
            "digest": digest,
            "rewritten": False,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
