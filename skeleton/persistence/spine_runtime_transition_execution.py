"""Compensable effectful runtime transition for the P2 deployment spine."""

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


class SpineRuntimeTransitionExecutionError(RuntimeError):
    """Effectful transition failed closed and attempted compensation."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionExecutionLedger:
    """Execute one slot swap + dispatcher start + fence advance per verified boundary."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_runtime_transition_execution (
                execution_id TEXT PRIMARY KEY,
                rollback_digest TEXT NOT NULL UNIQUE,
                transition_id TEXT NOT NULL UNIQUE,
                deployment_id TEXT NOT NULL,
                target_driver TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                prepared_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN ('prepared','executed','compensated','failed')
                ),
                fence_epoch_before INTEGER NOT NULL,
                fence_epoch_after INTEGER,
                slot_generation_before INTEGER NOT NULL,
                slot_generation_after INTEGER,
                payload_digest TEXT
            )
            """
        )
        self._connection.commit()

    def execute(
        self,
        *,
        rollback_witness: dict[str, Any],
        rollback_verify: dict[str, Any],
        slot: SpineRuntimeSlot,
        candidate_runtime: DurableOperationRuntime,
        fence: SQLiteConsistencyFence,
        tenant_id: str,
        resource_id: str,
        expected_epoch: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(rollback_witness, dict)
            or rollback_witness.get("kind") != "spine_runtime_transition_rollback_witness"
            or rollback_witness.get("rollback_verified") is not True
            or rollback_witness.get("rollback_required") is not False
            or rollback_witness.get("transition_attempted") is not True
            or rollback_witness.get("transition_executed") is not False
            or rollback_witness.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionExecutionError(
                "verified no-effect rollback boundary is required"
            )
        rollback_digest = rollback_witness.get("digest")
        transition_id = rollback_witness.get("transition_id")
        attempt_id = rollback_witness.get("attempt_id")
        deployment_id = rollback_witness.get("deployment_id")
        for field, value in (
            ("rollback digest", rollback_digest),
            ("transition identity", transition_id),
            ("attempt identity", attempt_id),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionExecutionError(f"{field} is invalid")
        if not isinstance(deployment_id, str) or not deployment_id or len(deployment_id) > 192:
            raise SpineRuntimeTransitionExecutionError("deployment identity is invalid")
        if rollback_witness.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionExecutionError("transition target driver changed")
        if (
            not isinstance(rollback_verify, dict)
            or rollback_verify.get("kind") != "spine_runtime_transition_rollback_verify"
            or rollback_verify.get("verified") is not True
            or rollback_verify.get("rollback_digest") != rollback_digest
            or rollback_verify.get("attempt_id") != attempt_id
            or rollback_verify.get("transition_executed") is not False
            or rollback_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionExecutionError(
                "independent no-effect rollback verification is required"
            )
        if not isinstance(slot, SpineRuntimeSlot):
            raise SpineRuntimeTransitionExecutionError("runtime slot is required")
        if not isinstance(candidate_runtime, DurableOperationRuntime):
            raise SpineRuntimeTransitionExecutionError("candidate runtime must be durable")
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineRuntimeTransitionExecutionError("consistency fence is required")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise SpineRuntimeTransitionExecutionError("tenant identity is required")
        if not isinstance(resource_id, str) or not resource_id:
            raise SpineRuntimeTransitionExecutionError("resource identity is required")
        if isinstance(expected_epoch, bool) or not isinstance(expected_epoch, int) or expected_epoch < 1:
            raise SpineRuntimeTransitionExecutionError("expected fence epoch must be positive")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeTransitionExecutionError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)

        generation_before = slot.generation
        execution_id = hashlib.sha256(
            (
                f"{rollback_digest}|{transition_id}|{deployment_id}|"
                f"{tenant_id}|{resource_id}|pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        try:
            self._connection.execute(
                """
                INSERT INTO spine_runtime_transition_execution(
                    execution_id,rollback_digest,transition_id,deployment_id,
                    target_driver,tenant_id,resource_id,prepared_at,status,
                    fence_epoch_before,slot_generation_before
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    execution_id,
                    rollback_digest,
                    transition_id,
                    deployment_id,
                    "pymongo-async",
                    tenant_id,
                    resource_id,
                    instant.isoformat(),
                    "prepared",
                    expected_epoch,
                    generation_before,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineRuntimeTransitionExecutionError(
                "transition execution replay refused"
            ) from exc

        original_runtime = slot.runtime
        replacement = None
        moved = None
        compensation_errors: list[str] = []
        try:
            if candidate_runtime is original_runtime:
                raise SpineRuntimeTransitionExecutionError(
                    "candidate runtime must be distinct"
                )
            if original_runtime.dispatcher_running:
                raise SpineRuntimeTransitionExecutionError(
                    "original dispatcher must be stopped"
                )
            if candidate_runtime.dispatcher_running:
                raise SpineRuntimeTransitionExecutionError(
                    "candidate dispatcher must be stopped"
                )
            replacement = slot.replace(
                expected=original_runtime,
                replacement=candidate_runtime,
            )
            started = candidate_runtime.start_dispatcher()
            if started is not True or candidate_runtime.dispatcher_running is not True:
                raise SpineRuntimeTransitionExecutionError(
                    "candidate dispatcher did not start"
                )
            if slot.runtime is not candidate_runtime:
                raise SpineRuntimeTransitionExecutionError(
                    "runtime slot did not retain candidate"
                )
            moved = fence.compare_and_advance(
                tenant_id=tenant_id,
                resource_id=resource_id,
                expected_epoch=expected_epoch,
                writer_id=f"runtime-transition:{deployment_id}",
                now=instant,
            )
            if moved.epoch != expected_epoch + 1:
                raise SpineRuntimeTransitionExecutionError(
                    "transition fence did not advance exactly once"
                )

            evidence = {
                "execution_id": execution_id,
                "rollback_digest": rollback_digest,
                "attempt_id": attempt_id,
                "transition_id": transition_id,
                "deployment_id": deployment_id,
                "target_driver": "pymongo-async",
                "tenant_id": tenant_id,
                "resource_id": resource_id,
                "executed_at": instant.isoformat(),
                "fence_epoch_before": expected_epoch,
                "fence_epoch_after": moved.epoch,
                "slot_generation_before": replacement["generation_before"],
                "slot_generation_after": replacement["generation_after"],
                "transition_executed": True,
                "runtime_driver_selected": True,
                "runtime_object_replaced": True,
                "dispatcher_started": True,
                "dispatcher_running": True,
                "fence_moved": True,
                "rollback_required": True,
                "runtime_activated": False,
            }
            payload_digest = _digest(evidence)
            cursor = self._connection.execute(
                """
                UPDATE spine_runtime_transition_execution
                SET status='executed',fence_epoch_after=?,
                    slot_generation_after=?,payload_digest=?
                WHERE execution_id=? AND status='prepared'
                """,
                (
                    moved.epoch,
                    replacement["generation_after"],
                    payload_digest,
                    execution_id,
                ),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise SpineRuntimeTransitionExecutionError(
                    "durable execution state changed before commit"
                )
            self._connection.commit()
            return {
                "kind": "spine_runtime_transition_execution",
                "hit": True,
                "law": "verified-boundary-executes-one-compensable-runtime-transition",
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
                if candidate_runtime.dispatcher_running:
                    candidate_runtime.stop_dispatcher(timeout_s=2.0, flush=False)
            except Exception as stop_exc:
                compensation_errors.append(type(stop_exc).__name__)
            try:
                if slot.runtime is candidate_runtime:
                    slot.restore(
                        expected_candidate=candidate_runtime,
                        original=original_runtime,
                    )
            except Exception as restore_exc:
                compensation_errors.append(type(restore_exc).__name__)
            if moved is not None:
                try:
                    fence.compare_and_advance(
                        tenant_id=tenant_id,
                        resource_id=resource_id,
                        expected_epoch=moved.epoch,
                        writer_id=f"runtime-compensate:{deployment_id}",
                    )
                except Exception as fence_exc:
                    compensation_errors.append(type(fence_exc).__name__)
            status = "compensated" if not compensation_errors else "failed"
            try:
                self._connection.execute(
                    """
                    UPDATE spine_runtime_transition_execution
                    SET status=? WHERE execution_id=? AND status='prepared'
                    """,
                    (status, execution_id),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
            detail = (
                ""
                if not compensation_errors
                else f"; compensation errors={','.join(compensation_errors)}"
            )
            raise SpineRuntimeTransitionExecutionError(
                f"effectful transition failed closed{detail}"
            ) from exc

    def status(self, execution_id: str) -> str:
        row = self._connection.execute(
            """
            SELECT status FROM spine_runtime_transition_execution
            WHERE execution_id=?
            """,
            (execution_id,),
        ).fetchone()
        if row is None:
            raise SpineRuntimeTransitionExecutionError(
                "unknown transition execution"
            )
        return str(row["status"])

    def close(self) -> None:
        self._connection.close()
