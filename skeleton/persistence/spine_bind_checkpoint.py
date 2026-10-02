"""Immutable SQLite checkpoint for a bind recovery plan.

A tenant may seal one recovery digest. Replaying the same digest is idempotent;
attempting to rewrite that tenant to a different recovery digest fails closed.
The checkpoint is evidence only and never activates the runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


class SpineBindCheckpointError(RuntimeError):
    """Bind checkpoint rejected its inputs. Not a maturity signal."""


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SpineBindCheckpointError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


def _recovery_digest(card: dict[str, Any]) -> str:
    expected = card.get("digest")
    if not isinstance(expected, str) or len(expected) != 64:
        raise SpineBindCheckpointError("recovery digest missing")
    body = {key: value for key, value in card.items() if key != "digest"}
    actual = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if actual != expected:
        raise SpineBindCheckpointError("recovery digest mismatch")
    return expected


class SpineBindCheckpoint:
    """Seal one immutable recovery checkpoint per tenant."""

    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_bind_checkpoint (
                tenant_id TEXT PRIMARY KEY,
                recovery_digest TEXT NOT NULL,
                snapshot_digest TEXT NOT NULL,
                sealed_at TEXT NOT NULL,
                activated INTEGER NOT NULL,
                apply_landed INTEGER NOT NULL,
                live_motor INTEGER NOT NULL,
                dispatcher_running INTEGER NOT NULL,
                ci_green INTEGER NOT NULL,
                merged INTEGER NOT NULL
            )
            """
        )
        self._connection.commit()

    def append(
        self,
        recovery: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(recovery, dict) or recovery.get("kind") != "spine_bind_recovery":
            raise SpineBindCheckpointError("recovery must be a spine_bind_recovery")
        tenant_id = recovery.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindCheckpointError("recovery tenant missing")
        if recovery.get("ready") is not False or recovery.get("activated") is not False:
            raise SpineBindCheckpointError("recovery unexpectedly ready")
        for flag in (
            "apply_landed",
            "live_motor",
            "dispatcher_running",
            "provider_surface_green",
            "pr_automation_green",
            "ci_green",
            "merged",
        ):
            if recovery.get(flag) is not False:
                raise SpineBindCheckpointError("recovery is not dark")
        recovery_digest = _recovery_digest(recovery)
        snapshot_digest = recovery.get("snapshot_digest")
        if not isinstance(snapshot_digest, str) or len(snapshot_digest) != 64:
            raise SpineBindCheckpointError("snapshot digest missing")
        instant = _aware(now or datetime.now(timezone.utc))

        existing = self._connection.execute(
            """
            SELECT recovery_digest, snapshot_digest, sealed_at
            FROM spine_bind_checkpoint
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchone()
        inserted = existing is None
        if existing is not None:
            if (
                existing["recovery_digest"] != recovery_digest
                or existing["snapshot_digest"] != snapshot_digest
            ):
                raise SpineBindCheckpointError("checkpoint rewrite")
            sealed_at = existing["sealed_at"]
        else:
            sealed_at = instant.isoformat()
            self._connection.execute(
                """
                INSERT INTO spine_bind_checkpoint (
                    tenant_id, recovery_digest, snapshot_digest, sealed_at,
                    activated, apply_landed, live_motor, dispatcher_running,
                    ci_green, merged
                ) VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0)
                """,
                (tenant_id, recovery_digest, snapshot_digest, sealed_at),
            )
            self._connection.commit()

        return {
            "kind": "spine_bind_checkpoint",
            "hit": True,
            "law": "checkpoint-is-immutable-and-unactivated",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "recovery_digest": recovery_digest,
            "snapshot_digest": snapshot_digest,
            "sealed_at": sealed_at,
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

    def read(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindCheckpointError("tenant_id must be non-empty text")
        row = self._connection.execute(
            """
            SELECT recovery_digest, snapshot_digest, sealed_at, activated,
                   apply_landed, live_motor, dispatcher_running, ci_green, merged
            FROM spine_bind_checkpoint
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchone()
        if row is None:
            return {
                "kind": "spine_bind_checkpoint",
                "hit": False,
                "law": "checkpoint-is-immutable-and-unactivated",
                "citation": "VOL-134",
                "tenant_id": tenant_id,
                "seen": False,
                "stored_prose": 0,
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }
        flags = ("activated", "apply_landed", "live_motor", "dispatcher_running", "ci_green", "merged")
        if any(int(row[name]) != 0 for name in flags):
            raise SpineBindCheckpointError("checkpoint row is not dark")
        return {
            "kind": "spine_bind_checkpoint",
            "hit": True,
            "law": "checkpoint-is-immutable-and-unactivated",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seen": True,
            "recovery_digest": row["recovery_digest"],
            "snapshot_digest": row["snapshot_digest"],
            "sealed_at": row["sealed_at"],
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
            "SELECT COUNT(*) AS n FROM spine_bind_checkpoint WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
