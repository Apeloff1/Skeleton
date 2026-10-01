from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_runtime_production_activation import (
    SpineRuntimeProductionActivationError,
    SpineRuntimeProductionActivationLedger,
)
from skeleton.persistence.spine_runtime_production_activation_authorization import (
    SpineRuntimeProductionActivationAuthorizationLedger,
)
from skeleton.persistence.spine_runtime_production_activation_authorization_verify import (
    SpineRuntimeProductionActivationAuthorizationVerify,
)
from skeleton.persistence.spine_runtime_production_activation_verify import (
    SpineRuntimeProductionActivationVerify,
)
from skeleton.persistence.spine_runtime_transition_acceptance import (
    SpineRuntimeTransitionAcceptanceLedger,
)
from skeleton.persistence.spine_runtime_transition_acceptance_verify import (
    SpineRuntimeTransitionAcceptanceVerify,
)
from skeleton.persistence.spine_runtime_transition_effect_rollback import (
    SpineRuntimeTransitionEffectRollbackLedger,
)
from skeleton.persistence.spine_runtime_transition_execution import (
    SpineRuntimeTransitionExecutionLedger,
)
from skeleton.persistence.spine_runtime_transition_execution_verify import (
    SpineRuntimeTransitionExecutionVerify,
)
from skeleton.persistence.spine_runtime_transition_health import (
    SpineRuntimeTransitionHealth,
)
from skeleton.persistence.spine_runtime_transition_health_verify import (
    SpineRuntimeTransitionHealthVerify,
)
from skeleton.persistence.spine_runtime_transition_slot import SpineRuntimeSlot


NOW = datetime(2026, 10, 1, 18, 30, tzinfo=timezone.utc)


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


def test_exact_authorized_health_activates_once_and_keeps_rollback_live(
    tmp_path: Path,
) -> None:
    original = _runtime(tmp_path, "activation-original")
    candidate = _runtime(tmp_path, "activation-candidate")
    fence = SQLiteConsistencyFence(tmp_path / "activation-fence.sqlite")
    token = fence.open(
        tenant_id="tenant-a",
        resource_id="runtime:deploy-a",
        writer_id="bootstrap",
    )
    slot = SpineRuntimeSlot(original)
    execution_ledger = SpineRuntimeTransitionExecutionLedger(
        tmp_path / "activation-execution.sqlite"
    )
    acceptance_ledger = SpineRuntimeTransitionAcceptanceLedger(
        tmp_path / "activation-acceptance.sqlite"
    )
    authorization_ledger = SpineRuntimeProductionActivationAuthorizationLedger(
        tmp_path / "activation-authorization.sqlite"
    )
    activation_ledger = SpineRuntimeProductionActivationLedger(
        tmp_path / "activation.sqlite"
    )
    rollback_ledger = SpineRuntimeTransitionEffectRollbackLedger(
        tmp_path / "activation-rollback.sqlite"
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
            now=NOW,
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
            now=NOW,
        )
        health_verify = SpineRuntimeTransitionHealthVerify().verify(
            health,
            slot=slot,
            candidate_runtime=candidate,
            fence=fence,
        )
        acceptance_receipt = {
            "kind": "spine_runtime_transition_acceptance_receipt",
            "authority_domain": "runtime-transition-acceptance",
            "decision": "accept-transition-health",
            "health_digest": health["digest"],
            "execution_id": execution["execution_id"],
            "deployment_id": "deploy-a",
            "target_driver": "pymongo-async",
            "acceptance_nonce": "n" * 64,
            "issued_at": (NOW - timedelta(seconds=10)).isoformat(),
            "expires_at": (NOW + timedelta(seconds=90)).isoformat(),
            "attestation_digest": "c" * 64,
        }
        acceptance = acceptance_ledger.accept(
            health=health,
            health_verify=health_verify,
            receipt=acceptance_receipt,
            authenticate=lambda receipt: receipt["attestation_digest"] == "c" * 64,
            now=NOW,
        )
        acceptance_verify = SpineRuntimeTransitionAcceptanceVerify().verify(
            acceptance
        )
        authorization_receipt = {
            "kind": "spine_runtime_production_activation_receipt",
            "authority_domain": "runtime-production-activation",
            "decision": "authorize-production-activation",
            "acceptance_digest": acceptance["digest"],
            "acceptance_id": acceptance["acceptance_id"],
            "execution_id": execution["execution_id"],
            "deployment_id": "deploy-a",
            "target_driver": "pymongo-async",
            "authorization_nonce": "u" * 64,
            "issued_at": (NOW - timedelta(seconds=5)).isoformat(),
            "expires_at": (NOW + timedelta(seconds=60)).isoformat(),
            "attestation_digest": "d" * 64,
        }
        authorization = authorization_ledger.authorize(
            acceptance=acceptance,
            acceptance_verify=acceptance_verify,
            receipt=authorization_receipt,
            authenticate=lambda receipt: receipt["attestation_digest"] == "d" * 64,
            now=NOW,
        )
        authorization_verify = (
            SpineRuntimeProductionActivationAuthorizationVerify().verify(
                authorization
            )
        )
        activation = activation_ledger.activate(
            authorization=authorization,
            authorization_verify=authorization_verify,
            health=health,
            health_verify=health_verify,
            slot=slot,
            candidate_runtime=candidate,
            fence=fence,
            now=NOW,
        )
        verified = SpineRuntimeProductionActivationVerify().verify(
            activation,
            slot=slot,
            candidate_runtime=candidate,
            fence=fence,
        )

        assert activation_ledger.count() == 1
        assert activation["authorization_consumed"] is True
        assert activation["runtime_activated"] is True
        assert activation["rollback_available"] is True
        assert activation["fence_moved_during_activation"] is False
        assert verified["verified"] is True
        assert slot.runtime is candidate
        assert candidate.dispatcher_running is True
        assert fence.read(
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
        ).epoch == execution["fence_epoch_after"]

        with pytest.raises(
            SpineRuntimeProductionActivationError,
            match="authorization replay refused",
        ):
            activation_ledger.activate(
                authorization=authorization,
                authorization_verify=authorization_verify,
                health=health,
                health_verify=health_verify,
                slot=slot,
                candidate_runtime=candidate,
                fence=fence,
                now=NOW,
            )

        rollback = rollback_ledger.rollback(
            execution=execution,
            execution_verify=execution_verify,
            slot=slot,
            original_runtime=original,
            candidate_runtime=candidate,
            fence=fence,
            now=NOW,
        )
        assert rollback["rollback_executed"] is True
        assert rollback["runtime_object_restored"] is True
        assert slot.runtime is original
        assert candidate.dispatcher_running is False
        assert fence.read(
            tenant_id="tenant-a",
            resource_id="runtime:deploy-a",
        ).epoch == execution["fence_epoch_after"] + 1
    finally:
        if candidate.dispatcher_running:
            candidate.stop_dispatcher(flush=False)
        candidate.close()
        original.close()
        fence.close()
        rollback_ledger.close()
        activation_ledger.close()
        authorization_ledger.close()
        acceptance_ledger.close()
        execution_ledger.close()


def test_activation_rejects_expired_authorization(tmp_path: Path) -> None:
    original = _runtime(tmp_path, "expired-original")
    candidate = _runtime(tmp_path, "expired-candidate")
    slot = SpineRuntimeSlot(original)
    fence = SQLiteConsistencyFence(tmp_path / "expired-fence.sqlite")
    ledger = SpineRuntimeProductionActivationLedger(
        tmp_path / "expired-activation.sqlite"
    )
    try:
        authorization = {
            "kind": "spine_runtime_production_activation_authorization",
            "authorization_id": "a" * 64,
            "digest": "d" * 64,
            "health_digest": "h" * 64,
            "execution_id": "e" * 64,
            "deployment_id": "deploy-a",
            "target_driver": "pymongo-async",
            "valid_until": (NOW - timedelta(seconds=1)).isoformat(),
            "authorization_authenticated": True,
            "activation_accepted": True,
            "production_activation_authorized": True,
            "rollback_available": True,
            "runtime_activated": False,
        }
        authorization_verify = {
            "kind": "spine_runtime_production_activation_authorization_verify",
            "authorization_id": "a" * 64,
            "authorization_digest": "d" * 64,
            "health_digest": "h" * 64,
            "execution_id": "e" * 64,
            "verified": True,
            "production_activation_authorized": True,
            "rollback_available": True,
            "runtime_activated": False,
        }
        health = {
            "kind": "spine_runtime_transition_health",
            "digest": "h" * 64,
            "execution_id": "e" * 64,
            "deployment_id": "deploy-a",
            "target_driver": "pymongo-async",
            "health_qualified": True,
            "operation_continuity": True,
            "dispatcher_running": True,
            "fence_stable": True,
            "rollback_available": True,
            "runtime_activated": False,
        }
        health_verify = {
            "kind": "spine_runtime_transition_health_verify",
            "health_digest": "h" * 64,
            "execution_id": "e" * 64,
            "verified": True,
            "operation_continuity": True,
            "rollback_available": True,
            "runtime_activated": False,
        }
        with pytest.raises(
            SpineRuntimeProductionActivationError,
            match="authorization expired",
        ):
            ledger.activate(
                authorization=authorization,
                authorization_verify=authorization_verify,
                health=health,
                health_verify=health_verify,
                slot=slot,
                candidate_runtime=candidate,
                fence=fence,
                now=NOW,
            )
    finally:
        candidate.close()
        original.close()
        fence.close()
        ledger.close()
