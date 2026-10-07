"""Replay verification for an immutable bind checkpoint."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


class SpineBindCheckpointReplayError(RuntimeError):
    """Checkpoint replay rejected its inputs. Not a maturity signal."""


class SpineBindCheckpointReplay:
    """Prove replay does not insert, rewrite, or activate a checkpoint."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def replay(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(checkpoint, dict) or checkpoint.get("kind") != "spine_bind_checkpoint":
            raise SpineBindCheckpointReplayError("checkpoint must be a spine_bind_checkpoint")
        tenant_id = checkpoint.get("tenant_id")
        digest = checkpoint.get("recovery_digest")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindCheckpointReplayError("checkpoint tenant missing")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SpineBindCheckpointReplayError("checkpoint digest missing")
        if checkpoint.get("activated") is not False:
            raise SpineBindCheckpointReplayError("checkpoint is activated")

        before = self._count(tenant_id)
        try:
            row = self._connection.execute(
                """
                SELECT recovery_digest, activated, apply_landed, live_motor,
                       dispatcher_running, ci_green, merged
                FROM spine_bind_checkpoint
                WHERE tenant_id = ?
                """,
                (tenant_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindCheckpointReplayError("checkpoint journal missing") from exc
        if row is None:
            raise SpineBindCheckpointReplayError("checkpoint row missing")
        if row["recovery_digest"] != digest:
            raise SpineBindCheckpointReplayError("checkpoint replay digest mismatch")
        for flag in ("activated", "apply_landed", "live_motor", "dispatcher_running", "ci_green", "merged"):
            if int(row[flag]) != 0:
                raise SpineBindCheckpointReplayError("checkpoint row is not dark")
        after = self._count(tenant_id)
        if before != after:
            raise SpineBindCheckpointReplayError("checkpoint replay inserted a row")
        return {
            "kind": "spine_bind_checkpoint_replay",
            "hit": True,
            "law": "checkpoint-replay-does-not-insert",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "recovery_digest": digest,
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
                "SELECT COUNT(*) AS n FROM spine_bind_checkpoint WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise SpineBindCheckpointReplayError("checkpoint journal missing") from exc
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
