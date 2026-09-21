from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_architecture_map import (
    ARCHITECTURE_PATH,
    REPO_ROOT,
    _normalized_repo_path,
    _validate_runtime_dag,
    validate_architecture,
)


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
