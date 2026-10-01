"""Compensating rollback for an effectful P2 runtime transition."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.spine_runtime_transition_slot import SpineRuntimeSlot


class SpineRuntimeTransitionEffectRollbackError(RuntimeError):
    """Effect rollback failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionEffectRollbackLedger:
    """Stop candidate, restore original runtime, and advance compensation fence."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_runtime_transition_effect_rollback (
                rollback_id TEXT PRIMARY KEY,
                execution_digest TEXT NOT NULL UNIQUE,
                execution_id TEXT NOT NULL UNIQUE,
                transition_id TEXT NOT NULL,
                deployment_id TEXT NOT NULL,
                prepared_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN ('prepared','rolled_back','failed')
                ),
                rollback_epoch_before INTEGER NOT NULL,
                rollback_epoch_after INTEGER,
                slot_generation_before INTEGER NOT NULL,
                slot_generation_after INTEGER,
                payload_digest TEXT
            )
            """
        )
        self._connection.commit()

    def rollback(
        self,
        *,
        execution: dict[str, Any],
        execution_verify: dict[str, Any],
        slot: SpineRuntimeSlot,
        original_runtime: DurableOperationRuntime,
        candidate_runtime: DurableOperationRuntime,
        fence: SQLiteConsistencyFence,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(execution, dict)
            or execution.get("kind") != "spine_runtime_transition_execution"
            or execution.get("transition_executed") is not True
            or execution.get("runtime_object_replaced") is not True
            or execution.get("dispatcher_running") is not True
            or execution.get("fence_moved") is not True
            or execution.get("rollback_required") is not True
            or execution.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionEffectRollbackError(
                "verified effectful execution is required"
            )
        execution_digest = execution.get("digest")
        execution_id = execution.get("execution_id")
        transition_id = execution.get("transition_id")
        deployment_id = execution.get("deployment_id")
        for field, value in (
            ("execution digest", execution_digest),
            ("execution identity", execution_id),
            ("transition identity", transition_id),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionEffectRollbackError(
                    f"{field} is invalid"
                )
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeTransitionEffectRollbackError(
                "deployment identity is missing"
            )
        if (
            not isinstance(execution_verify, dict)
            or execution_verify.get("kind") != "spine_runtime_transition_execution_verify"
            or execution_verify.get("verified") is not True
            or execution_verify.get("execution_id") != execution_id
            or execution_verify.get("execution_digest") != execution_digest
            or execution_verify.get("transition_executed") is not True
            or execution_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionEffectRollbackError(
                "independent execution verification is required"
            )
        if not isinstance(slot, SpineRuntimeSlot):
            raise SpineRuntimeTransitionEffectRollbackError(
                "runtime slot is required"
            )
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineRuntimeTransitionEffectRollbackError(
                "consistency fence is required"
            )

        rollback_epoch_before = execution.get("fence_epoch_after")
        if (
            isinstance(rollback_epoch_before, bool)
            or not isinstance(rollback_epoch_before, int)
            or rollback_epoch_before < 2
        ):
            raise SpineRuntimeTransitionEffectRollbackError(
                "execution fence epoch is invalid"
            )
        resource_id = execution.get("resource_id")
        tenant_id = execution.get("tenant_id")
        if not isinstance(resource_id, str) or not resource_id:
            raise SpineRuntimeTransitionEffectRollbackError(
                "resource identity is missing"
            )
        if not isinstance(tenant_id, str) or not tenant_id:
            raise SpineRuntimeTransitionEffectRollbackError(
                "tenant identity is missing"
            )

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeTransitionEffectRollbackError(
                "now must be timezone-aware"
            )
        instant = instant.astimezone(timezone.utc)

        generation_before = slot.generation
        rollback_id = hashlib.sha256(
            (
                f"{execution_digest}|{execution_id}|{deployment_id}|"
                f"{resource_id}|pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        try:
            self._connection.execute(
                """
                INSERT INTO spine_runtime_transition_effect_rollback(
                    rollback_id,execution_digest,execution_id,transition_id,
                    deployment_id,prepared_at,status,rollback_epoch_before,
                    slot_generation_before
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    rollback_id,
                    execution_digest,
                    execution_id,
                    transition_id,
                    deployment_id,
                    instant.isoformat(),
                    "prepared",
                    rollback_epoch_before,
                    generation_before,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineRuntimeTransitionEffectRollbackError(
                "effect rollback replay refused"
            ) from exc

        moved = None
        try:
            if slot.runtime is not candidate_runtime:
                raise SpineRuntimeTransitionEffectRollbackError(
                    "runtime slot is not on executed candidate"
                )
            if candidate_runtime.dispatcher_running is not True:
                raise SpineRuntimeTransitionEffectRollbackError(
                    "candidate dispatcher is not running"
                )
            if original_runtime.dispatcher_running:
                raise SpineRuntimeTransitionEffectRollbackError(
                    "original dispatcher unexpectedly running"
                )
            candidate_runtime.stop_dispatcher(timeout_s=2.0, flush=False)
            if candidate_runtime.dispatcher_running:
                raise SpineRuntimeTransitionEffectRollbackError(
                    "candidate dispatcher did not stop"
                )
            restored = slot.restore(
                expected_candidate=candidate_runtime,
                original=original_runtime,
            )
            if slot.runtime is not original_runtime:
                raise SpineRuntimeTransitionEffectRollbackError(
                    "runtime slot did not restore original"
                )
            moved = fence.compare_and_advance(
                tenant_id=tenant_id,
                resource_id=resource_id,
                expected_epoch=rollback_epoch_before,
                writer_id=f"runtime-rollback:{deployment_id}",
                now=instant,
            )
            if moved.epoch != rollback_epoch_before + 1:
                raise SpineRuntimeTransitionEffectRollbackError(
                    "rollback compensation fence did not advance exactly once"
                )

            evidence = {
                "rollback_id": rollback_id,
                "execution_id": execution_id,
                "execution_digest": execution_digest,
                "transition_id": transition_id,
                "deployment_id": deployment_id,
                "target_driver": "pymongo-async",
                "tenant_id": tenant_id,
                "resource_id": resource_id,
                "rolled_back_at": instant.isoformat(),
                "rollback_epoch_before": rollback_epoch_before,
                "rollback_epoch_after": moved.epoch,
                "slot_generation_before": restored["generation_before"],
                "slot_generation_after": restored["generation_after"],
                "rollback_executed": True,
                "runtime_object_restored": True,
                "candidate_dispatcher_stopped": True,
                "original_dispatcher_running": False,
                "fence_compensated": True,
                "transition_executed": True,
                "runtime_activated": False,
            }
            payload_digest = _digest(evidence)
            cursor = self._connection.execute(
                """
                UPDATE spine_runtime_transition_effect_rollback
                SET status='rolled_back',rollback_epoch_after=?,
                    slot_generation_after=?,payload_digest=?
                WHERE rollback_id=? AND status='prepared'
                """,
                (
                    moved.epoch,
                    restored["generation_after"],
                    payload_digest,
                    rollback_id,
                ),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise SpineRuntimeTransitionEffectRollbackError(
                    "durable rollback state changed before commit"
                )
            self._connection.commit()
            return {
                "kind": "spine_runtime_transition_effect_rollback",
                "hit": True,
                "law": "effectful-transition-rollback-restores-runtime-and-compensates-fence",
                "citation": "VOL-134",
                **evidence,
                "digest": payload_digest,
                "stored_prose": 0,
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }
        except Exception as exc:
            try:
                if moved is None and slot.runtime is original_runtime:
                    slot.replace(
                        expected=original_runtime,
                        replacement=candidate_runtime,
                    )
                    if not candidate_runtime.dispatcher_running:
                        candidate_runtime.start_dispatcher()
            except Exception:
                pass
            try:
                self._connection.execute(
                    """
                    UPDATE spine_runtime_transition_effect_rollback
                    SET status='failed'
                    WHERE rollback_id=? AND status='prepared'
                    """,
                    (rollback_id,),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
            raise SpineRuntimeTransitionEffectRollbackError(
                "effect rollback failed closed"
            ) from exc

    def status(self, rollback_id: str) -> str:
        row = self._connection.execute(
            """
            SELECT status FROM spine_runtime_transition_effect_rollback
            WHERE rollback_id=?
            """,
            (rollback_id,),
        ).fetchone()
        if row is None:
            raise SpineRuntimeTransitionEffectRollbackError(
                "unknown effect rollback"
            )
        return str(row["status"])

    def close(self) -> None:
        self._connection.close()
