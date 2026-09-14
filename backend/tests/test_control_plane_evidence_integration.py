import asyncio

from core.product_control_plane import ProductControlPlane


def test_bound_admission_transitions_from_pending_to_confirmed(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="studio",
        domain="studio",
        action="project.create",
        principal="creator",
        actor_weight=0,
        payload={"title": "Evidence project"},
        idempotency_key="evidence-project",
    )

    pending = plane.operation_lifecycle(admitted.id)
    assert pending["state"] == "pending_bound"
    assert pending["confidence"] == "high"
    assert pending["receipt_present"] is False

    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is True
    confirmed = plane.operation_lifecycle(admitted.id)
    assert confirmed["state"] == "confirmed"
    assert confirmed["receipt_present"] is True
    assert confirmed["executed_audit_present"] is True
    assert confirmed["pending"] is False


def test_unbound_operation_is_visible_as_unbound_evidence(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="studio",
        domain="studio",
        action="build.submit",
        principal="creator",
        actor_weight=0,
        payload={"target": "linux"},
    )
    lifecycle = plane.operation_lifecycle(admitted.id)
    assert lifecycle["state"] == "pending_unbound"
    assert lifecycle["executor_bound"] is False


def test_execution_ledger_reconstructs_multiple_operations(tmp_path):
    plane = ProductControlPlane(tmp_path)
    bound = plane.admit(
        capability_id="studio", domain="studio", action="project.create",
        principal="creator", actor_weight=0, payload={"title": "A"},
    )
    unbound = plane.admit(
        capability_id="studio", domain="studio", action="build.submit",
        principal="creator", actor_weight=0, payload={"target": "linux"},
    )
    asyncio.run(plane.execute_registered(bound.outbox_seq))

    ledger = {item["operation_id"]: item for item in plane.execution_ledger()}
    assert ledger[bound.id]["state"] == "confirmed"
    assert ledger[unbound.id]["state"] == "pending_unbound"
    status = plane.status()
    assert status["lifecycle"]["operations"] >= 2
    assert status["lifecycle"]["states"]["confirmed"] >= 1
    assert status["lifecycle"]["states"]["pending_unbound"] >= 1
    assert status["lifecycle"]["evidence_gaps"] == 0
