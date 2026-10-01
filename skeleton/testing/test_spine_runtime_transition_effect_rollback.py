from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_runtime_transition_effect_rollback import (
    SpineRuntimeTransitionEffectRollbackError,
    SpineRuntimeTransitionEffectRollbackLedger,
)
from skeleton.persistence.spine_runtime_transition_effect_rollback_verify import (
    SpineRuntimeTransitionEffectRollbackVerify,
    SpineRuntimeTransitionEffectRollbackVerifyError,
)
from skeleton.persistence.spine_runtime_transition_execution import (
    SpineRuntimeTransitionExecutionLedger,
)
from skeleton.persistence.spine_runtime_transition_execution_verify import (
    SpineRuntimeTransitionExecutionVerify,
)
from skeleton.persistence.spine_runtime_transition_slot import SpineRuntimeSlot


class _Reasoner:
    def reason(self, **kwargs):
        return {"answer": "ok"}


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


def _execute(
    tmp_path: Path,
) -> tuple[
    DurableOperationRuntime,
    DurableOperationRuntime,
    SQLiteConsistencyFence,
    SpineRuntimeSlot,
    SpineRuntimeTransitionExecutionLedger,
    dict[str, object],
    dict[str, object],
]:
    original = _runtime(tmp_path, "rollback-original")
    candidate = _runtime(tmp_path, "rollback-candidate")
    fence = SQLiteConsistencyFence(tmp_path / "rollback-fence.sqlite")
    token = fence.open(
        tenant_id="tenant-a",
        resource_id="runtime:deploy-a",
        writer_id="bootstrap",
    )
    slot = SpineRuntimeSlot(original)
    execution_ledger = SpineRuntimeTransitionExecutionLedger(
        tmp_path / "rollback-execution.sqlite"
    )
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
    execution_verify = SpineRuntimeTransitionExecutionVerify().verify(execution)
    return (
        original,
        candidate,
        fence,
        slot,
        execution_ledger,
        execution,
        execution_verify,
    )


def test_effect_rollback_restores_runtime_stops_candidate_and_compensates_fence(
    tmp_path: Path,
) -> None:
    (
        original,
        candidate,
        fence,
        slot,
        execution_ledger,
        execution,
        execution_verify,
    ) = _execute(tmp_path)
    rollback_ledger = SpineRuntimeTransitionEffectRollbackLedger(
        tmp_path / "effect-rollback.sqlite"
    )
    try:
        card = rollback_ledger.rollback(
            execution=execution,
            execution_verify=execution_verify,
            slot=slot,
            original_runtime=original,
            candidate_runtime=candidate,
            fence=fence,
        )
        verified = SpineRuntimeTransitionEffectRollbackVerify().verify(card)

        assert slot.runtime is original
        assert slot.generation == 2
        assert candidate.dispatcher_running is False
        assert original.dispatcher_running is False
        assert fence.read(
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
        ).epoch == execution["fence_epoch_after"] + 1
        assert card["rollback_executed"] is True
        assert card["runtime_object_restored"] is True
        assert card["candidate_dispatcher_stopped"] is True
        assert card["fence_compensated"] is True
        assert card["runtime_activated"] is False
        assert verified["verified"] is True

        with pytest.raises(
            SpineRuntimeTransitionEffectRollbackError,
            match="replay refused",
        ):
            rollback_ledger.rollback(
                execution=execution,
                execution_verify=execution_verify,
                slot=slot,
                original_runtime=original,
                candidate_runtime=candidate,
                fence=fence,
            )
    finally:
        candidate.close()
        original.close()
        fence.close()
        rollback_ledger.close()
        execution_ledger.close()


def test_effect_rollback_verifier_rejects_activation_tamper(
    tmp_path: Path,
) -> None:
    (
        original,
        candidate,
        fence,
        slot,
        execution_ledger,
        execution,
        execution_verify,
    ) = _execute(tmp_path)
    rollback_ledger = SpineRuntimeTransitionEffectRollbackLedger(
        tmp_path / "effect-rollback-verify.sqlite"
    )
    try:
        card = rollback_ledger.rollback(
            execution=execution,
            execution_verify=execution_verify,
            slot=slot,
            original_runtime=original,
            candidate_runtime=candidate,
            fence=fence,
        )
        card["runtime_activated"] = True
        with pytest.raises(
            SpineRuntimeTransitionEffectRollbackVerifyError,
            match="cannot assert activation",
        ):
            SpineRuntimeTransitionEffectRollbackVerify().verify(card)
    finally:
        candidate.close()
        original.close()
        fence.close()
        rollback_ledger.close()
        execution_ledger.close()
