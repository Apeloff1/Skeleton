from __future__ import annotations

import json
from pathlib import Path

from scripts.check_ai_app_construction import CONTRACT_PATH, ROOT, validate_construction
from scripts.check_provider_bootstrap import validate_provider_bootstrap


def _contract() -> dict:
    return json.loads((ROOT / CONTRACT_PATH).read_text(encoding="utf-8"))


def test_complete_ai_construction_contract_is_valid() -> None:
    errors, summary = validate_construction(ROOT)

    assert errors == []
    assert summary["ok"] is True
    assert summary["architecture_tag"] == "arch-map/v3.7"
    assert summary["construction_version"] == "3.7.0"
    assert summary["planes"] >= 26
    assert summary["runtime_providers"] == ["openai"]
    assert summary["automation_providers"] == ["repository-automation"]
    assert summary["provider_surfaces"] >= 6


def test_provider_bootstrap_is_fail_closed_and_materialized() -> None:
    contract = _contract()
    bootstrap = contract["provider_bootstrap"]

    assert bootstrap["mandatory"] is True
    assert bootstrap["mode"] == "fail_closed"
    assert bootstrap["runtime_enforcement"]["receipt_required"] is True
    assert bootstrap["runtime_enforcement"]["undeclared_provider_policy"] == "deny"
    assert validate_provider_bootstrap(ROOT) == []


def test_every_partial_plane_has_an_explicit_gap() -> None:
    contract = _contract()
    partial = {plane["id"] for plane in contract["planes"] if plane["state"] == "partial"}
    gap_planes = {
        gap["plane"]
        for gap in contract["gap_register"]
        if gap["status"] == "open"
    }

    assert partial
    assert partial <= gap_planes


def test_p0_gaps_are_explicitly_blocking_sota_completion() -> None:
    contract = _contract()
    p0 = [
        gap
        for gap in contract["gap_register"]
        if gap["priority"] == "P0" and gap["status"] == "open"
    ]

    assert p0
    assert contract["gap_closure_policy"]["p0_gaps_block_sota_complete"] is True
    assert all(gap["construction"] for gap in p0)
    assert all(gap["closure_evidence"] for gap in p0)


def test_construction_phases_cover_each_plane_once() -> None:
    contract = _contract()
    plane_ids = {plane["id"] for plane in contract["planes"]}
    scheduled = [
        plane_id
        for phase in contract["construction_phases"]
        for plane_id in phase["planes"]
    ]

    assert len(scheduled) == len(set(scheduled))
    assert set(scheduled) == plane_ids


def test_provider_documents_all_point_to_canonical_sources() -> None:
    contract = _contract()
    must_read = contract["provider_bootstrap"]["must_read"]

    for entry in contract["provider_bootstrap"]["development_provider_entrypoints"]:
        text = (ROOT / entry["path"]).read_text(encoding="utf-8")
        for relative in must_read:
            assert relative in text


def test_no_required_evidence_path_is_virtual() -> None:
    contract = _contract()

    for plane in contract["planes"]:
        assert (ROOT / plane["owner"]).exists(), plane["id"]
        for relative in plane["evidence"]:
            assert (ROOT / relative).exists(), (plane["id"], relative)


def test_credential_bearing_provider_surfaces_are_declared_and_receipt_gated() -> None:
    contract = _contract()
    credential_surfaces = [
        surface
        for surface in contract["provider_surfaces"]
        if surface["credential_bearing"] is True
    ]

    assert credential_surfaces
    credential_owners = {
        surface["owner"]
        for surface in credential_surfaces
    }
    assert credential_owners >= {
        "skeleton/provider_runtime.py",
        "skeleton/automation/free_model.py",
    }
    assert "backend/core/ai_provider.py" not in credential_owners
    assert "skeleton/jeeves/providers.py" not in credential_owners
    assert all(surface["receipt_required"] is True for surface in credential_surfaces)
    assert all((ROOT / surface["owner"]).is_file() for surface in credential_surfaces)


def test_provider_families_have_one_shared_receipt_contract() -> None:
    contract = _contract()
    enforcement = contract["provider_bootstrap"]["runtime_enforcement"]

    assert enforcement["loader"] == "skeleton/provider_contract.py"
    assert enforcement["activation_boundary"] == "skeleton/provider_runtime.py"
    assert set(enforcement["compatibility_boundaries"]) == {
        "backend/core/ai_provider.py",
        "skeleton/jeeves/providers.py",
    }
    assert set(enforcement["provider_families"]) == {
        "runtime_model",
        "automation_model",
    }
    assert enforcement["undeclared_provider_policy"] == "deny"


def test_model_provider_plane_is_engine_owned() -> None:
    contract = _contract()
    provider_plane = next(
        plane for plane in contract["planes"] if plane["id"] == "model-provider"
    )
    openai = next(
        provider
        for provider in contract["runtime_model_providers"]
        if provider["id"] == "openai"
    )

    assert provider_plane["owner"] == "skeleton/provider_runtime.py"
    assert "skeleton/provider_runtime.py" in provider_plane["evidence"]
    assert openai["adapter"] == "skeleton/provider_runtime.py:OpenAIProviderAdapter"
    assert openai["sync_adapter"] == "skeleton/provider_runtime.py:OpenAISyncProviderAdapter"
    assert openai["compatibility_facade"] == "backend/core/ai_provider.py"


def test_operation_and_stream_architecture_is_materialized() -> None:
    errors, summary = validate_construction(ROOT)
    contract = _contract()

    assert errors == []
    assert summary["operation_stream"] == {
        "operation_owner": "skeleton/contracts/operation.py",
        "stream_owner": "skeleton/frontier/operation_stream.py",
        "durable_store": "skeleton/frontier/operation_stream_store.py",
        "stream_schema_version": 1,
    }

    operation = contract["operation_contract"]
    assert operation["owner"] == "skeleton/contracts/operation.py"
    assert set(operation["terminal_states"]) == {
        "completed",
        "failed",
        "cancelled",
    }

    stream = contract["stream_protocol"]
    assert stream["transport_neutral"] is True
    assert stream["schema_version"] == 1
    assert (
        stream["durable_reference_store"]
        == "skeleton/frontier/operation_stream_store.py:SQLiteOperationEventStore"
    )

    operation_fields = set(
        contract["canonical_envelopes"]["operation"]["required_fields"]
    )
    assert {
        "operation_id",
        "tenant_id",
        "actor_id",
        "capability",
        "created_at",
        "deadline",
        "idempotency_key",
        "trace_id",
    } <= operation_fields

    stream_fields = set(
        contract["canonical_envelopes"]["stream_event"]["required_fields"]
    )
    assert {
        "operation_id",
        "event_id",
        "sequence",
        "type",
        "timestamp",
        "payload",
    } <= stream_fields


def test_stream_gap_tracks_only_unfinished_transport_and_client_work() -> None:
    contract = _contract()
    gap = next(
        item
        for item in contract["gap_register"]
        if item["id"] == "gap-streaming-protocol"
    )
    package = next(
        item
        for item in contract["construction_work_packages"]
        if item["id"] == "WP-P0-STREAM"
    )

    assert gap["status"] == "open"
    assert package["progress"]["state"] == "in_progress"
    assert "durable SQLite operation event store" in package["progress"]["completed"]
    assert "durable stream storage adapter" not in package["progress"]["remaining"]
    assert "backend SSE or WebSocket transport" in package["progress"]["remaining"]
    assert "frontend reconnect/resume cursor" in package["progress"]["remaining"]


def test_dependency_and_acceptance_relationships_are_separate() -> None:
    contract = _contract()
    planes = {plane["id"]: plane for plane in contract["planes"]}

    assert contract["relationship_semantics"]["runtime_dependency"]["field"] == "depends_on"
    assert contract["relationship_semantics"]["acceptance_target"]["field"] == "validates"
    assert planes["model-routing"]["owner"] == "skeleton/frontier/model_routing.py"
    assert "model-routing" in planes["orchestration"]["depends_on"]

    release = planes["deployment-release"]
    assert "application-api" not in release["depends_on"]
    assert "product-experience" not in release["depends_on"]
    assert set(release["validates"]) == {
        "application-api",
        "engine-api",
        "product-experience",
    }


def test_functional_ai_closure_matches_exact_p0_set_and_dependency_dag() -> None:
    contract = _contract()
    closure = contract["functional_ai_closure"]
    graph = contract["functional_ai_dependency_graph"]

    declared_p0 = {
        gap["id"]
        for gap in contract["gap_register"]
        if gap["priority"] == "P0"
    }
    required_p0 = set(closure["required_p0_gaps"])
    graph_p0 = {node["gap"] for node in graph["nodes"]}
    staged_p0 = {
        gap_id
        for stage in graph["stages"]
        for gap_id in stage["closes"]
    }

    assert declared_p0
    assert required_p0 == declared_p0
    assert graph_p0 == declared_p0
    assert staged_p0 == declared_p0

    node_by_gap = {node["gap"]: node for node in graph["nodes"]}
    for node in graph["nodes"]:
        for dependency in node["depends_on"]:
            assert dependency in declared_p0
            assert node_by_gap[dependency]["stage"] < node["stage"]


def test_functional_ai_blueprints_are_bound_to_p0_gaps_and_work_packages() -> None:
    contract = _contract()
    closure = contract["functional_ai_closure"]
    gaps = {gap["id"]: gap for gap in contract["gap_register"]}
    packages = {
        package["id"]: package
        for package in contract["construction_work_packages"]
    }
    planes = {plane["id"]: plane for plane in contract["planes"]}

    for item in closure["required_blueprints"]:
        blueprint = contract[item["key"]]
        gap = gaps[item["gap"]]
        package = packages[item["work_package"]]

        assert blueprint["schema_version"] == 1
        assert blueprint["gap"] == item["gap"]
        assert gap["priority"] == "P0"
        assert gap["plane"] == item["plane"]
        assert package["gap"] == item["gap"]
        if gap["status"] == "open":
            assert planes[item["plane"]]["state"] == "partial"


def test_functional_ai_required_envelopes_exist() -> None:
    contract = _contract()
    closure = contract["functional_ai_closure"]
    envelopes = contract["canonical_envelopes"]

    assert set(closure["required_envelopes"]) <= set(envelopes)
    for envelope_id in closure["required_envelopes"]:
        required_fields = envelopes[envelope_id]["required_fields"]
        assert required_fields
        assert len(required_fields) == len(set(required_fields))


def test_functional_ai_dependency_stage_contract_is_contiguous_and_unique() -> None:
    contract = _contract()
    graph = contract["functional_ai_dependency_graph"]
    stages = graph["stages"]

    numbers = [stage["stage"] for stage in stages]
    assert numbers == list(range(len(stages)))

    closed = [
        gap_id
        for stage in stages
        for gap_id in stage["closes"]
    ]
    assert len(closed) == len(set(closed))


def test_fully_functional_ai_core_planes_remain_partial_while_p0_gaps_are_open() -> None:
    contract = _contract()
    closure_p0 = set(contract["functional_ai_closure"]["required_p0_gaps"])
    planes = {plane["id"]: plane for plane in contract["planes"]}

    for gap in contract["gap_register"]:
        if gap["id"] in closure_p0 and gap["status"] == "open":
            assert planes[gap["plane"]]["state"] == "partial"
