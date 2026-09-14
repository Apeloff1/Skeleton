import asyncio

from core.product_control_plane import ProductControlPlane


def test_default_executor_registry_binds_native_actions(tmp_path):
    plane = ProductControlPlane(tmp_path)
    bindings = {(item["capability_id"], item["action"]) for item in plane.executors.snapshot()}
    assert ("studio", "project.create") in bindings
    assert ("studio", "pipeline.inspect") in bindings
    assert ("world-forge", "world.create") in bindings
    assert ("world-forge", "world.systems.compose") in bindings
    assert ("playables", "playable.launch") in bindings
    assert ("playables", "runtime.sessions") in bindings
    assert ("operations", "ops.runtime") in bindings
    assert ("governance", "governance.policy") in bindings
    assert ("governance", "governance.audit") in bindings
    assert ("governance", "governance.safety") in bindings
    assert ("studio", "build.submit") not in bindings


def test_studio_project_executes_and_writes_provenance_receipt(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="studio", domain="studio", action="project.create", principal="creator",
        actor_weight=0, payload={"title": "Native project", "genre": "rpg", "brief": "build it"},
        idempotency_key="studio-native-1",
    )
    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is True
    assert plane.operations.outbox.pending_count == 0
    receipt = plane.receipt(admitted.id)
    assert receipt is not None
    assert receipt["executor"] == "native.studio.project.create"
    assert receipt["executor_version"] == 1
    assert receipt["replay_safe"] is True
    assert receipt["input_artifact_manifest_id"] == admitted.artifact_manifest_id
    result = plane.receipts.load_result(admitted.id)
    assert result["title"] == "Native project"
    assert result["state"] == "created"


def test_world_system_compiler_executes_through_governed_queue(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="world-forge",
        domain="world-forge",
        action="world.systems.compose",
        principal="world-architect",
        actor_weight=0,
        payload={"world": {"name": "Atlas", "stats": {"river_tiles": 4, "settlements": 2}, "entities": [1]}},
        idempotency_key="compose-atlas-1",
    )
    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is True
    result = plane.receipt_result(admitted.id)
    blueprint = result["blueprint"]
    assert len(blueprint["blueprint_sha256"]) == 64
    assert len(blueprint["world_signature"]) == 64
    assert "environment.hydrology" in blueprint["execution_order"]
    assert "population.settlements" in blueprint["execution_order"]
    receipt = plane.receipt(admitted.id)
    assert receipt["executor"] == "native.worldforge.world.systems.compose"
    assert receipt["replay_safe"] is True


def test_playable_launch_executes_real_runtime_session(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="playables", domain="playables", action="playable.launch", principal="player",
        actor_weight=0, payload={"seed": 7, "resolution": 12, "thermal_count": 1}, idempotency_key="launch-7",
    )
    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is True
    result = plane.receipts.load_result(admitted.id)
    assert result["session_id"]
    assert result["runtime"]["active"] == 1


def test_unbound_build_action_stays_pending(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(capability_id="studio", domain="studio", action="build.submit",
                           principal="creator", actor_weight=0, payload={"build_id": "b1"})
    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is False
    assert plane.operations.outbox.pending_count == 1
    assert plane.receipt(admitted.id) is None


def test_executor_retry_uses_existing_receipt_without_duplicate_session(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(capability_id="playables", domain="playables", action="playable.launch",
                           principal="player", actor_weight=0,
                           payload={"seed": 9, "resolution": 12, "thermal_count": 1})
    operation = plane.operations.pending_operations()[0]
    payload = plane.operations.load_payload(operation)
    executor = plane.executors.executor_for(operation)
    assert executor(operation, payload) is True
    first_receipt = plane.receipt(admitted.id)
    active_before = plane.native_executors.sessions.snapshot()["active"]
    assert executor(operation, payload) is True
    assert plane.native_executors.sessions.snapshot()["active"] == active_before
    assert plane.receipt(admitted.id) == first_receipt


def test_receipt_store_keeps_result_payload_out_of_receipt_file(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(capability_id="studio", domain="studio", action="project.create",
                           principal="creator", actor_weight=0,
                           payload={"title": "Compact receipt", "brief": "x" * 10_000})
    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is True
    receipt_path = tmp_path / "receipts" / f"{admitted.id}.json"
    text = receipt_path.read_text(encoding="utf-8")
    assert "x" * 1_000 not in text
    assert plane.receipts.stats()["results"]["manifests"] == 1
