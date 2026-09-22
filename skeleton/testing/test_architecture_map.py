from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.check_architecture_map import (
    ARCHITECTURE_PATH,
    REPO_ROOT,
    _normalized_repo_path,
    _validate_runtime_dag,
    _validate_structural_blueprint,
    _validate_zone_dag,
    validate_architecture,
)
from scripts.check_source_path_inventory import classify_path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_architecture_contract_is_valid() -> None:
    errors, summary = validate_architecture(REPO_ROOT)

    assert errors == []
    assert summary["ok"] is True
    assert summary["architecture_tag"].startswith("arch-map/")
    assert summary["canonical_roots"] >= 8
    assert summary["zones"] >= 8
    assert summary["runtime_nodes"] == 5


def test_runtime_nodes_exactly_match_app_manifest_services() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    runtime = _load(REPO_ROOT / "skeleton/app/manifest.json")

    nodes = {node["id"]: node for node in architecture["runtime_nodes"]}
    services = {service["name"]: service for service in runtime["services"]}

    assert set(nodes) == set(services)
    for name, node in nodes.items():
        service = services[name]
        assert node["manifest_service"] == name
        assert node["path"] == service["path"]
        assert node["kind"] == service["kind"]
        assert node["canonical"] == service["canonical"]
        assert node["depends_on"] == service["depends_on"]


def test_runtime_order_places_dependencies_before_consumers() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    nodes = {node["id"]: node for node in architecture["runtime_nodes"]}
    errors: list[str] = []

    order = _validate_runtime_dag(nodes, errors)
    positions = {node_id: index for index, node_id in enumerate(order)}

    assert errors == []
    for node_id, node in nodes.items():
        for dependency in node["depends_on"]:
            assert positions[dependency] < positions[node_id]


def test_change_routing_keeps_architecture_on_every_live_lane() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)

    for route in architecture["change_routing"]:
        assert route["paths"]
        assert "architecture-map" in route["minimum_checks"]


@pytest.mark.parametrize(
    "value",
    [
        "../outside",
        "/absolute/path",
        "machine//architecture.json",
        "./machine/architecture.json",
        "machine\\architecture.json",
        "",
    ],
)
def test_architecture_paths_reject_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError):
        _normalized_repo_path(value)


def test_runtime_cycle_is_rejected() -> None:
    nodes = {
        "a": {"depends_on": ["c"]},
        "b": {"depends_on": ["a"]},
        "c": {"depends_on": ["b"]},
    }
    errors: list[str] = []

    order = _validate_runtime_dag(nodes, errors)

    assert order == []
    assert errors
    assert "cycle" in errors[0]


def test_architecture_sources_link_all_contract_layers() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)

    assert architecture["sources"] == {
            "runtime_contract": "skeleton/app/manifest.json",
            "repository_contract": "machine/manifest.json",
            "human_map": "docs/ARCHITECTURE_MAP.md",
            "validator": "scripts/check_architecture_map.py",
            "construction_contract": "machine/ai_app_construction.json",
            "construction_manual": "docs/AI_APP_CONSTRUCTION_MANUAL.md",
            "construction_validator": "scripts/check_ai_app_construction.py",
            "provider_bootstrap_validator": "scripts/check_provider_bootstrap.py",
            "provider_contract": "skeleton/provider_contract.py",
            "operation_contract": "skeleton/contracts/operation.py",
            "stream_contract": "skeleton/frontier/operation_stream.py",
            "stream_store": "skeleton/frontier/operation_stream_store.py",
            "capability_interface_registry": "machine/capability_interfaces.json",
            "capability_interface_validator": "scripts/check_capability_interfaces.py",
            "state_topology": "machine/state_topology.json",
            "state_topology_validator": "scripts/check_state_topology.py",
            "ai_runtime_schema_catalog": "machine/ai_runtime_schemas.json",
            "ai_implementation_handoff": "machine/ai_implementation_handoff.json",
            "ai_closure_evidence": "machine/ai_closure_evidence.json",
            "ai_capability_registry": "machine/ai_capabilities.json",
            "ai_file_tree": "machine/ai_file_tree.json"
        }


def test_no_new_runtime_root_can_be_implicit() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    policy = architecture["top_level_policy"]
    roots = {root["path"]: root for root in architecture["canonical_roots"]}

    assert policy["new_runtime_root"] == "forbidden-unless-declared"
    for runtime_root in policy["runtime_roots"]:
        assert runtime_root in roots
        assert roots[runtime_root]["class"] in {"runtime", "accelerator"}


def test_runtime_manifest_links_back_to_active_architecture() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    runtime = _load(REPO_ROOT / "skeleton/app/manifest.json")

    assert runtime["architecture"] == {
        "contract": "machine/architecture.json",
        "validator": architecture["sources"]["validator"],
        "documentation": architecture["sources"]["human_map"],
        "tag": architecture["architecture_tag"],
        "structure_tag": architecture["structural_blueprint"]["structure_tag"],
    }


def test_top_level_policy_is_disjoint_and_materialized() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    policy = architecture["top_level_policy"]
    categories = (
        "runtime_roots",
        "control_roots",
        "evidence_roots",
        "transitional_roots",
        "legacy_root_entrypoints",
    )

    seen: set[str] = set()
    for category in categories:
        for relative in policy[category]:
            assert relative not in seen
            seen.add(relative)
            assert (REPO_ROOT / relative).exists()


def test_zone_dependency_graph_is_acyclic() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    zones = {zone["id"]: zone for zone in architecture["zones"]}
    errors: list[str] = []

    order = _validate_zone_dag(zones, errors)
    positions = {zone_id: index for index, zone_id in enumerate(order)}

    assert errors == []
    assert set(order) == set(zones)
    for zone_id, zone in zones.items():
        for dependency in zone["may_depend_on"]:
            assert positions[dependency] < positions[zone_id]


def test_transitional_roots_are_not_canonical_source_inventory() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    transitional = architecture["top_level_policy"]["transitional_roots"]

    assert "core" in transitional
    assert classify_path("core/activation_security.py") == "first-party"
    assert classify_path("eval/fixtures/example.json") == "fixture"

def test_structural_blueprint_partitions_every_construction_plane() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    construction = _load(REPO_ROOT / "machine/ai_app_construction.json")
    blueprint = architecture["structural_blueprint"]

    plane_ids = {plane["id"] for plane in construction["planes"]}
    placements = blueprint["plane_placements"]
    placed_ids = [placement["plane"] for placement in placements]
    recovery_ids = [
        plane_id
        for domain in blueprint["recovery_domains"]
        for plane_id in domain["planes"]
    ]

    assert blueprint["structure_tag"] == "structure-map/v1.3"
    assert len(placed_ids) == len(set(placed_ids))
    assert set(placed_ids) == plane_ids
    assert len(recovery_ids) == len(set(recovery_ids))
    assert set(recovery_ids) == plane_ids


def test_structural_plane_owners_match_construction_and_zone_roots() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    construction = _load(REPO_ROOT / "machine/ai_app_construction.json")
    zones = {zone["id"]: zone for zone in architecture["zones"]}
    planes = {plane["id"]: plane for plane in construction["planes"]}

    for placement in architecture["structural_blueprint"]["plane_placements"]:
        plane = planes[placement["plane"]]
        assert placement["owner"] == plane["owner"]
        assert (REPO_ROOT / placement["owner"]).exists()
        assert any(
            placement["owner"] == root
            or placement["owner"].startswith(root + "/")
            for root in zones[placement["zone"]]["roots"]
        )


def test_structural_cross_zone_dependencies_follow_zone_dag_without_exceptions() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    construction = _load(REPO_ROOT / "machine/ai_app_construction.json")
    blueprint = architecture["structural_blueprint"]
    zones = {zone["id"]: zone for zone in architecture["zones"]}
    placements = {
        placement["plane"]: placement
        for placement in blueprint["plane_placements"]
    }

    assert blueprint["dependency_exceptions"] == []

    for plane in construction["planes"]:
        source_zone = placements[plane["id"]]["zone"]
        for dependency in plane["depends_on"]:
            target_zone = placements[dependency]["zone"]
            assert (
                source_zone == target_zone
                or target_zone in zones[source_zone]["may_depend_on"]
            ), (plane["id"], dependency)


def test_structural_validator_rejects_new_reverse_dependency_without_exception() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    broken = deepcopy(architecture)
    placement = next(
        item
        for item in broken["structural_blueprint"]["plane_placements"]
        if item["plane"] == "model-routing"
    )
    placement["zone"] = "application"
    placement["owner"] = "backend/core/model_router.py"
    zones = {zone["id"]: zone for zone in broken["zones"]}
    errors: list[str] = []

    _validate_structural_blueprint(broken, zones, REPO_ROOT, errors)

    assert any(
        "orchestration(engine) -> model-routing(application)" in error
        for error in errors
    )


def test_acceptance_edges_match_construction_validates_without_affecting_dag() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    construction = _load(REPO_ROOT / "machine/ai_app_construction.json")
    blueprint = architecture["structural_blueprint"]

    architecture_edges = {
        (item["source_plane"], item["target_plane"])
        for item in blueprint["acceptance_edges"]
    }
    construction_edges = {
        (plane["id"], target)
        for plane in construction["planes"]
        for target in plane.get("validates", [])
    }

    assert architecture_edges == construction_edges
    assert (
        "deployment-release",
        "product-experience",
    ) in architecture_edges


def test_structural_validator_rejects_owner_outside_declared_zone() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    broken = deepcopy(architecture)
    placement = next(
        item
        for item in broken["structural_blueprint"]["plane_placements"]
        if item["plane"] == "application-api"
    )
    placement["zone"] = "product"
    zones = {zone["id"]: zone for zone in broken["zones"]}
    errors: list[str] = []

    _validate_structural_blueprint(broken, zones, REPO_ROOT, errors)

    assert errors
    assert any(
        "application-api owner backend is outside zone product" in error
        for error in errors
    )


def test_architecture_summary_reports_deep_structure_counts() -> None:
    errors, summary = validate_architecture(REPO_ROOT)

    assert errors == []
    assert summary["structure"] == {
        "levels": 5,
        "plane_placements": 27,
        "composition_roots": 7,
        "state_authorities": 13,
        "recovery_domains": 8,
        "dependency_exceptions": 0,
        "acceptance_edges": 3,
        "execution_hosts": 4,
        "execution_profiles": 10,
        "plane_execution": 27,
        "startup_groups": 3,
        "shutdown_groups": 3,
    }


def test_repository_manifest_links_architecture_and_structure_tags() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    repository = _load(REPO_ROOT / "machine/manifest.json")
    assembly = repository["assembly"]
    layer = next(
        item
        for item in assembly["layers"]
        if item["name"] == "architecture-map"
    )

    assert assembly["architecture_contract"] == "machine/architecture.json"
    assert assembly["structure_tag"] == architecture["structural_blueprint"]["structure_tag"]
    assert layer["tag"] == architecture["architecture_tag"]
    assert layer["structure_tag"] == architecture["structural_blueprint"]["structure_tag"]
    assert layer["ref"] == assembly["architecture_branch"]

def test_execution_topology_covers_every_plane_once() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    construction = _load(REPO_ROOT / "machine/ai_app_construction.json")
    blueprint = architecture["structural_blueprint"]

    plane_ids = {plane["id"] for plane in construction["planes"]}
    executions = blueprint["plane_execution"]
    execution_planes = [item["plane"] for item in executions]
    profiles = {profile["id"] for profile in blueprint["execution_profiles"]}
    hosts = {host["id"] for host in blueprint["execution_hosts"]}

    assert len(execution_planes) == len(set(execution_planes))
    assert set(execution_planes) == plane_ids
    assert all(item["profile"] in profiles for item in executions)
    assert all(item["host"] in hosts for item in executions)


def test_execution_hosts_match_structural_placement_zones() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    blueprint = architecture["structural_blueprint"]
    placements = {
        item["plane"]: item
        for item in blueprint["plane_placements"]
    }
    hosts = {
        item["id"]: item
        for item in blueprint["execution_hosts"]
    }

    for execution in blueprint["plane_execution"]:
        plane = execution["plane"]
        assert execution["zone"] == placements[plane]["zone"]
        assert execution["zone"] in hosts[execution["host"]]["allowed_zones"]


def test_structural_validator_rejects_execution_host_zone_drift() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    broken = deepcopy(architecture)
    execution = next(
        item
        for item in broken["structural_blueprint"]["plane_execution"]
        if item["plane"] == "application-api"
    )
    execution["host"] = "frontend-client"
    zones = {zone["id"]: zone for zone in broken["zones"]}
    errors: list[str] = []

    _validate_structural_blueprint(broken, zones, REPO_ROOT, errors)

    assert any(
        "application-api zone application is not allowed by host frontend-client" in error
        for error in errors
    )

def test_runtime_lifecycle_covers_nodes_and_respects_dependency_order() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    lifecycle = architecture["structural_blueprint"]["runtime_lifecycle"]
    runtime_nodes = {
        node["id"]: node
        for node in architecture["runtime_nodes"]
    }
    startup_order = {
        node_id: group["order"]
        for group in lifecycle["startup_groups"]
        for node_id in group["nodes"]
    }
    shutdown_order = {
        node_id: group["order"]
        for group in lifecycle["shutdown_groups"]
        for node_id in group["nodes"]
    }

    assert set(startup_order) == set(runtime_nodes)
    assert set(shutdown_order) == set(runtime_nodes)
    for node_id, node in runtime_nodes.items():
        for dependency in node["depends_on"]:
            assert startup_order[dependency] < startup_order[node_id]
            assert shutdown_order[node_id] < shutdown_order[dependency]


def test_structural_validator_rejects_startup_dependency_in_same_group() -> None:
    architecture = _load(REPO_ROOT / ARCHITECTURE_PATH)
    broken = deepcopy(architecture)
    lifecycle = broken["structural_blueprint"]["runtime_lifecycle"]
    core = next(group for group in lifecycle["startup_groups"] if group["id"] == "core-services")
    product = next(group for group in lifecycle["startup_groups"] if group["id"] == "product-shell")
    core["nodes"].append("frontend")
    product["nodes"].remove("frontend")
    zones = {zone["id"]: zone for zone in broken["zones"]}
    errors: list[str] = []

    _validate_structural_blueprint(broken, zones, REPO_ROOT, errors)

    assert any(
        "startup order violates runtime dependency frontend->backend" in error
        or "startup order violates runtime dependency frontend->skeleton" in error
        for error in errors
    )
