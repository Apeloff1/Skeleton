import asyncio

from core.product_control_plane import ProductControlPlane
from core.product_executor_registry import ProductExecutorRegistry


def _admit(plane, capability, domain, action, key):
    return plane.admit(
        capability_id=capability,
        domain=domain,
        action=action,
        principal="tester",
        actor_weight=0,
        payload={"key": key},
        idempotency_key=key,
    )


def test_batch_dispatch_isolates_confirmed_deferred_unbound_and_failed(tmp_path):
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)
    success = _admit(plane, "studio", "studio", "project.create", "success")
    deferred = _admit(plane, "playables", "playables", "runtime.sessions", "deferred")
    unbound = _admit(plane, "studio", "studio", "build.submit", "unbound")
    failed = _admit(plane, "governance", "governance", "governance.policy", "failed")

    registry = ProductExecutorRegistry()
    registry.register("studio", "project.create", lambda op, payload: True, name="ok")
    registry.register("playables", "runtime.sessions", lambda op, payload: False, name="later")

    def explode(op, payload):
        raise RuntimeError("boom")

    registry.register("governance", "governance.policy", explode, name="broken")
    report = asyncio.run(plane.dispatch_pending(registry))

    assert report["attempted"] == 4
    assert report["confirmed"] == [success.outbox_seq]
    assert report["deferred"] == [deferred.outbox_seq]
    assert report["unbound"] == [unbound.outbox_seq]
    assert report["failed"][0]["outbox_seq"] == failed.outbox_seq
    assert report["remaining"] == 3


def test_lifecycle_moves_from_pending_bound_to_confirmed(tmp_path):
    plane = ProductControlPlane(tmp_path)
    operation = plane.admit(
        capability_id="studio",
        domain="studio",
        action="project.create",
        principal="creator",
        actor_weight=0,
        payload={"title": "Lifecycle"},
    )
    before = plane.operation_lifecycle(operation.id)
    assert before["state"] == "pending_bound"
    assert before["executor"]["replay_safe"] is True
    assert before["receipt"] is None

    assert asyncio.run(plane.execute_registered(operation.outbox_seq)) is True
    after = plane.operation_lifecycle(operation.id)
    assert after["state"] == "confirmed"
    assert after["pending"] is None
    assert after["receipt"]["result_artifact_id"]
    assert {entry["kind"] for entry in after["audit_events"]} >= {"operation_admitted", "operation_executed"}


def test_unbound_lifecycle_is_explicit(tmp_path):
    plane = ProductControlPlane(tmp_path)
    operation = plane.admit(
        capability_id="studio",
        domain="studio",
        action="build.submit",
        principal="creator",
        actor_weight=0,
        payload={"target": "linux"},
    )
    lifecycle = plane.operation_lifecycle(operation.id)
    assert lifecycle["state"] == "pending_unbound"
    assert lifecycle["executor"] is None
