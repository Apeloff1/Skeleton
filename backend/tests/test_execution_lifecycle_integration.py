import asyncio

from core.product_control_plane import ProductControlPlane
from core.product_executor_registry import ProductExecutorRegistry


def test_native_execution_moves_evidence_from_pending_to_confirmed_and_survives_restart(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="studio",
        domain="studio",
        action="project.create",
        principal="creator",
        actor_weight=0,
        payload={"title": "Lifecycle integration", "brief": "prove durable state"},
        idempotency_key="lifecycle-native-1",
    )

    pending = plane.operation_lifecycle(admitted.id)
    assert pending["state"] == "pending_bound"
    assert pending["pending"] is True
    assert pending["receipt_present"] is False
    assert pending["admitted_audit_present"] is True
    assert pending["executor"]["name"] == "native.studio.project.create"
    assert pending["anomalies"] == ()

    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is True

    confirmed = plane.operation_lifecycle(admitted.id)
    assert confirmed["state"] == "confirmed"
    assert confirmed["pending"] is False
    assert confirmed["receipt_present"] is True
    assert confirmed["executed_audit_present"] is True
    assert confirmed["executed_audit_count"] == 1
    assert confirmed["anomalies"] == ()
    assert len(confirmed["evidence_sha256"]) == 64
    assert confirmed["receipt"]["input_artifact_manifest_id"] == admitted.artifact_manifest_id

    restored = ProductControlPlane(tmp_path)
    replay = restored.operation_lifecycle(admitted.id)
    assert replay["state"] == "confirmed"
    assert replay["evidence_sha256"] == confirmed["evidence_sha256"]
    assert restored.receipt_result(admitted.id)["state"] == "created"


def test_unbound_operation_remains_durable_pending_evidence(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="studio",
        domain="studio",
        action="build.submit",
        principal="creator",
        actor_weight=0,
        payload={"build_id": "build-unbound-1"},
        idempotency_key="lifecycle-unbound-1",
    )

    report = asyncio.run(plane.dispatch_pending())
    assert report["unbound"] == [admitted.outbox_seq]
    assert report["confirmed"] == []
    assert report["remaining"] == 1

    lifecycle = plane.operation_lifecycle(admitted.id)
    assert lifecycle["state"] == "pending_unbound"
    assert lifecycle["pending"] is True
    assert lifecycle["executor_bound"] is False
    assert lifecycle["receipt_present"] is False
    assert lifecycle["admitted_audit_present"] is True
    assert lifecycle["anomalies"] == ()

    restored = ProductControlPlane(tmp_path)
    assert restored.operation_lifecycle(admitted.id)["state"] == "pending_unbound"


def test_receipt_without_execution_attestation_is_reported_as_anomaly(tmp_path):
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)
    admitted = plane.admit(
        capability_id="studio",
        domain="studio",
        action="project.create",
        principal="creator",
        actor_weight=0,
        payload={"title": "Premature receipt"},
    )
    plane.receipts.write(
        operation_id=admitted.id,
        capability_id=admitted.capability_id,
        action=admitted.action,
        executor="test.premature",
        executor_version=1,
        effect_class="state",
        replay_safe=True,
        input_artifact_manifest_id=admitted.artifact_manifest_id,
        result={"state": "created"},
    )

    lifecycle = plane.operation_lifecycle(admitted.id)
    assert lifecycle["state"] == "executed_unconfirmed"
    assert lifecycle["pending"] is True
    assert lifecycle["receipt_present"] is True
    assert lifecycle["executed_audit_present"] is False
    assert "receipt_without_execution_audit" in lifecycle["anomalies"]
    assert lifecycle["confidence"] == "medium"


def test_executor_failure_is_audited_and_intent_remains_retryable(tmp_path):
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)
    registry = ProductExecutorRegistry()

    def explode(_operation, _payload):
        raise RuntimeError("boom")

    registry.register(
        "studio",
        "project.create",
        explode,
        name="test.exploding",
        version=1,
        effect_class="state",
        replay_safe=True,
    )
    plane.executors = registry
    admitted = plane.admit(
        capability_id="studio",
        domain="studio",
        action="project.create",
        principal="creator",
        actor_weight=0,
        payload={"title": "Retry me"},
    )

    report = asyncio.run(plane.dispatch_pending())
    assert report["confirmed"] == []
    assert report["remaining"] == 1
    assert len(report["failed"]) == 1
    assert report["failed"][0]["operation_id"] == admitted.id

    lifecycle = plane.operation_lifecycle(admitted.id)
    assert lifecycle["state"] == "pending_bound"
    assert lifecycle["failed_audit_count"] == 1
    assert lifecycle["receipt_present"] is False
    assert lifecycle["executor"]["name"] == "test.exploding"
    assert lifecycle["anomalies"] == ()
