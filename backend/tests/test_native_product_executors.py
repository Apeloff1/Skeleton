import asyncio

from core.canonical_product_policy import CANONICAL_PRODUCT_POLICY
from core.product_control_plane import ProductControlPlane


def test_default_executor_registry_binds_native_actions(tmp_path):
    plane = ProductControlPlane(tmp_path)
    bindings = {(item["capability_id"], item["action"]) for item in plane.executors.snapshot()}
    assert ("studio", "project.create") in bindings
    assert ("studio", "pipeline.inspect") in bindings
    assert ("world-forge", "world.create") in bindings
    assert ("world-forge", "world.systems.compose") in bindings
    assert ("world-forge", "asset.forge") in bindings
    assert ("playables", "playable.launch") in bindings
    assert ("playables", "runtime.sessions") in bindings
    assert ("academy", "academy.continue") in bindings
    assert ("academy", "academy.practice") in bindings
    assert ("academy", "academy.progress") in bindings
    assert ("operations", "ops.agents") in bindings
    assert ("operations", "ops.runtime") in bindings
    assert ("governance", "governance.policy") in bindings
    assert ("governance", "governance.audit") in bindings
    assert ("governance", "governance.safety") in bindings
    assert ("studio", "build.submit") in bindings


def test_default_executor_registry_covers_entire_canonical_policy(tmp_path):
    plane = ProductControlPlane(tmp_path)
    bound = {(item["capability_id"], item["action"]) for item in plane.executors.snapshot()}
    canonical = {
        (domain.domain, action)
        for domain in CANONICAL_PRODUCT_POLICY
        for action in domain.actions
    }

    assert bound == canonical
    assert plane.executor_coverage()["coverage_pct"] == 100.0
    assert plane.readiness_report()["ready_pct"] == 100.0


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


def test_build_submit_executes_artifact_adapter_and_hides_internal_path(tmp_path, monkeypatch):
    seen = {}

    def fake_build(game_name, *, files=None, build_token=None, built_at=None):
        seen.update(game_name=game_name, files=files, build_token=build_token, built_at=built_at)
        return {
            "ok": True,
            "build_id": "demo-web-token",
            "game_name": "demo",
            "kind": "web",
            "path": "/internal/artifacts/demo.zip",
            "filename": "demo.zip",
            "size_bytes": 42,
            "sha256": "a" * 64,
            "download_url": "/api/gameforge/build/download/demo-web-token",
        }

    monkeypatch.setattr("core.product_default_executors.build_web_artifact", fake_build)
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="studio",
        domain="studio",
        action="build.submit",
        principal="creator",
        actor_weight=0,
        payload={"game_name": "demo", "kind": "web", "files": [{"filename": "main.js", "content": "ok"}]},
        idempotency_key="build-submit-1",
    )

    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is True
    result = plane.receipt_result(admitted.id)["build"]
    assert result["build_id"] == "demo-web-token"
    assert result["download_url"].startswith("/api/gameforge/build/download/")
    assert "path" not in result
    assert seen["game_name"] == "demo"
    assert seen["build_token"] == admitted.id
    assert seen["built_at"] > 0


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


def test_asset_forge_executes_with_supplied_gamefiles(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="world-forge",
        domain="world-forge",
        action="asset.forge",
        principal="artist",
        actor_weight=0,
        payload={
            "build_id": "asset-build-1",
            "persist": False,
            "items": [
                {
                    "item_id": "itm_tree",
                    "stage": "assets",
                    "skin": {
                        "palette": ["#336633", "#88AA55"],
                        "applied_choices": {"dimension": "2d"},
                    },
                }
            ],
        },
        idempotency_key="asset-forge-1",
    )

    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is True
    result = plane.receipt_result(admitted.id)["asset_forge"]
    assert result["build_id"] == "asset-build-1"
    assert result["items"] == 1
    assert result["total_assets"] > 0
    assert "assets" not in result


def test_ops_agents_executes_against_canonical_swarm_inventory(tmp_path):
    plane = ProductControlPlane(tmp_path)
    admitted = plane.admit(
        capability_id="operations",
        domain="operations",
        action="ops.agents",
        principal="operator",
        actor_weight=0,
        payload={"category": "rendering", "limit": 3},
        idempotency_key="ops-agents-1",
    )

    assert asyncio.run(plane.execute_registered(admitted.outbox_seq)) is True
    result = plane.receipt_result(admitted.id)["agents"]
    assert result["returned"] == 3
    assert result["total"] >= 3
    assert all(item["category"] == "rendering" for item in result["items"])
