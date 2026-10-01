from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_runtime_transition_execution import (
    SpineRuntimeTransitionExecutionError,
    SpineRuntimeTransitionExecutionLedger,
)
from skeleton.persistence.spine_runtime_transition_execution_verify import (
    SpineRuntimeTransitionExecutionVerify,
    SpineRuntimeTransitionExecutionVerifyError,
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


def _rollback_witness() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_rollback_witness",
        "digest": "b" * 64,
        "attempt_id": "a" * 64,
        "transition_id": "t" * 64,
        "deployment_id": "deploy-a",
        "target_driver": "pymongo-async",
        "rollback_checked": True,
        "rollback_required": False,
        "rollback_executed": False,
        "rollback_verified": True,
        "transition_attempted": True,
        "transition_executed": False,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_identity_stable": True,
        "dispatcher_started": False,
        "fence_moved": False,
        "runtime_activated": False,
    }


def _rollback_verify() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_rollback_verify",
        "rollback_digest": "b" * 64,
        "attempt_id": "a" * 64,
        "verified": True,
        "rollback_required": False,
        "rollback_verified": True,
        "transition_attempted": True,
        "transition_executed": False,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_started": False,
        "fence_moved": False,
        "runtime_activated": False,
    }


def test_effectful_transition_swaps_runtime_starts_dispatcher_and_moves_fence(
    tmp_path: Path,
) -> None:
    original = _runtime(tmp_path, "original")
    candidate = _runtime(tmp_path, "candidate")
    fence = SQLiteConsistencyFence(tmp_path / "fence.sqlite")
    token = fence.open(
        tenant_id="tenant-a",
        resource_id="runtime:deploy-a",
        writer_id="bootstrap",
    )
    slot = SpineRuntimeSlot(original)
    ledger = SpineRuntimeTransitionExecutionLedger(tmp_path / "execution.sqlite")
    try:
        card = ledger.execute(
            rollback_witness=_rollback_witness(),
            rollback_verify=_rollback_verify(),
            slot=slot,
            candidate_runtime=candidate,
            fence=fence,
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
            expected_epoch=token.epoch,
        )
        verified = SpineRuntimeTransitionExecutionVerify().verify(card)

        assert slot.runtime is candidate
        assert slot.generation == 1
        assert candidate.dispatcher_running is True
        assert original.dispatcher_running is False
        assert fence.read(
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
        ).epoch == token.epoch + 1
        assert card["transition_executed"] is True
        assert card["runtime_object_replaced"] is True
        assert card["dispatcher_started"] is True
        assert card["fence_moved"] is True
        assert card["runtime_activated"] is False
        assert verified["verified"] is True

        with pytest.raises(
            SpineRuntimeTransitionExecutionError,
            match="replay refused",
        ):
            ledger.execute(
                rollback_witness=_rollback_witness(),
                rollback_verify=_rollback_verify(),
                slot=slot,
                candidate_runtime=candidate,
                fence=fence,
                tenant_id="tenant-a",
                resource_id="runtime:deploy-a",
                expected_epoch=token.epoch + 1,
            )
    finally:
        if candidate.dispatcher_running:
            candidate.stop_dispatcher(flush=False)
        candidate.close()
        original.close()
        fence.close()
        ledger.close()


def test_effectful_transition_compensates_when_fence_cas_fails(
    tmp_path: Path,
) -> None:
    original = _runtime(tmp_path, "original-fail")
    candidate = _runtime(tmp_path, "candidate-fail")
    fence = SQLiteConsistencyFence(tmp_path / "fence-fail.sqlite")
    token = fence.open(
        tenant_id="tenant-a",
        resource_id="runtime:deploy-a",
        writer_id="bootstrap",
    )
    slot = SpineRuntimeSlot(original)
    ledger = SpineRuntimeTransitionExecutionLedger(tmp_path / "execution-fail.sqlite")
    try:
        with pytest.raises(
            SpineRuntimeTransitionExecutionError,
            match="effectful transition failed closed",
        ):
            ledger.execute(
                rollback_witness=_rollback_witness(),
                rollback_verify=_rollback_verify(),
                slot=slot,
                candidate_runtime=candidate,
                fence=fence,
                tenant_id="tenant-a",
                resource_id="runtime:deploy-a",
                expected_epoch=token.epoch + 1,
            )

        assert slot.runtime is original
        assert candidate.dispatcher_running is False
        assert original.dispatcher_running is False
        assert fence.read(
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
        ).epoch == token.epoch
    finally:
        candidate.close()
        original.close()
        fence.close()
        ledger.close()


def test_execution_verifier_rejects_activation_tamper(tmp_path: Path) -> None:
    original = _runtime(tmp_path, "original-verify")
    candidate = _runtime(tmp_path, "candidate-verify")
    fence = SQLiteConsistencyFence(tmp_path / "fence-verify.sqlite")
    token = fence.open(
        tenant_id="tenant-a",
        resource_id="runtime:deploy-a",
        writer_id="bootstrap",
    )
    slot = SpineRuntimeSlot(original)
    ledger = SpineRuntimeTransitionExecutionLedger(tmp_path / "execution-verify.sqlite")
    try:
        card = ledger.execute(
            rollback_witness=_rollback_witness(),
            rollback_verify=_rollback_verify(),
            slot=slot,
            candidate_runtime=candidate,
            fence=fence,
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
            expected_epoch=token.epoch,
        )
        card["runtime_activated"] = True
        with pytest.raises(
            SpineRuntimeTransitionExecutionVerifyError,
            match="cannot self-activate",
        ):
            SpineRuntimeTransitionExecutionVerify().verify(card)
    finally:
        if candidate.dispatcher_running:
            candidate.stop_dispatcher(flush=False)
        candidate.close()
        original.close()
        fence.close()
        ledger.close()
