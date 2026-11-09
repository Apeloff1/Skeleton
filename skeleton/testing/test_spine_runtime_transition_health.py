from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_runtime_transition_execution import (
    SpineRuntimeTransitionExecutionLedger,
)
from skeleton.persistence.spine_runtime_transition_execution_verify import (
    SpineRuntimeTransitionExecutionVerify,
)
from skeleton.persistence.spine_runtime_transition_health import (
    SpineRuntimeTransitionHealth,
    SpineRuntimeTransitionHealthError,
)
from skeleton.persistence.spine_runtime_transition_health_verify import (
    SpineRuntimeTransitionHealthVerify,
)
from skeleton.persistence.spine_runtime_transition_slot import SpineRuntimeSlot


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok", "confidence": 1.0}


def _runtime(root: Path, name: str) -> DurableOperationRuntime:
    return DurableOperationRuntime(
        _Reasoner(),
        SQLiteOperationStore(root / f"{name}-operations.sqlite"),
        SQLiteOperationEventStore(root / f"{name}-events.sqlite"),
        outbox_dispatch_interval_s=0.05,
    )


def _witness() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_rollback_witness",
        "digest": "b" * 64,
        "attempt_id": "a" * 64,
        "transition_id": "t" * 64,
        "deployment_id": "deploy-a",
        "target_driver": "pymongo-async",
        "rollback_verified": True,
        "rollback_required": False,
        "transition_attempted": True,
        "transition_executed": False,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_started": False,
        "fence_moved": False,
        "runtime_activated": False,
    }


def _witness_verify() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_rollback_verify",
        "rollback_digest": "b" * 64,
        "attempt_id": "a" * 64,
        "verified": True,
        "transition_executed": False,
        "runtime_activated": False,
    }


def test_live_health_proves_operation_continuity_without_activation(
    tmp_path: Path,
) -> None:
    original = _runtime(tmp_path, "health-original")
    candidate = _runtime(tmp_path, "health-candidate")
    fence = SQLiteConsistencyFence(tmp_path / "health-fence.sqlite")
    token = fence.open(
        tenant_id="tenant-a",
        resource_id="runtime:deploy-a",
        writer_id="bootstrap",
    )
    slot = SpineRuntimeSlot(original)
    execution_ledger = SpineRuntimeTransitionExecutionLedger(
        tmp_path / "health-execution.sqlite"
    )
    try:
        execution = execution_ledger.execute(
            rollback_witness=_witness(),
            rollback_verify=_witness_verify(),
            slot=slot,
            candidate_runtime=candidate,
            fence=fence,
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
            expected_epoch=token.epoch,
        )
        execution_verify = SpineRuntimeTransitionExecutionVerify().verify(
            execution
        )
        health = SpineRuntimeTransitionHealth().probe(
            execution=execution,
            execution_verify=execution_verify,
            slot=slot,
            candidate_runtime=candidate,
            fence=fence,
        )
        verified = SpineRuntimeTransitionHealthVerify().verify(
            health,
            slot=slot,
            candidate_runtime=candidate,
            fence=fence,
        )

        assert health["health_qualified"] is True
        assert health["operation_continuity"] is True
        assert health["pending_outbox"] == 0
        assert health["dispatcher_running"] is True
        assert health["fence_stable"] is True
        assert health["rollback_available"] is True
        assert health["runtime_activated"] is False
        assert verified["verified"] is True
    finally:
        if candidate.dispatcher_running:
            candidate.stop_dispatcher(flush=False)
        candidate.close()
        original.close()
        fence.close()
        execution_ledger.close()


def test_live_health_rejects_fence_drift(tmp_path: Path) -> None:
    original = _runtime(tmp_path, "drift-original")
    candidate = _runtime(tmp_path, "drift-candidate")
    fence = SQLiteConsistencyFence(tmp_path / "drift-fence.sqlite")
    token = fence.open(
        tenant_id="tenant-a",
        resource_id="runtime:deploy-a",
        writer_id="bootstrap",
    )
    slot = SpineRuntimeSlot(original)
    execution_ledger = SpineRuntimeTransitionExecutionLedger(
        tmp_path / "drift-execution.sqlite"
    )
    try:
        execution = execution_ledger.execute(
            rollback_witness=_witness(),
            rollback_verify=_witness_verify(),
            slot=slot,
            candidate_runtime=candidate,
            fence=fence,
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
            expected_epoch=token.epoch,
        )
        execution_verify = SpineRuntimeTransitionExecutionVerify().verify(
            execution
        )
        fence.compare_and_advance(
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
            expected_epoch=execution["fence_epoch_after"],
            writer_id="external-drift",
        )
        with pytest.raises(
            SpineRuntimeTransitionHealthError,
            match="fence epoch changed",
        ):
            SpineRuntimeTransitionHealth().probe(
                execution=execution,
                execution_verify=execution_verify,
                slot=slot,
                candidate_runtime=candidate,
                fence=fence,
            )
    finally:
        if candidate.dispatcher_running:
            candidate.stop_dispatcher(flush=False)
        candidate.close()
        original.close()
        fence.close()
        execution_ledger.close()
