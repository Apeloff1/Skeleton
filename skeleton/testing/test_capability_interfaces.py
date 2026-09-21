from __future__ import annotations

import json
from pathlib import Path

from scripts.check_capability_interfaces import (
    ARCHITECTURE_PATH,
    CONSTRUCTION_PATH,
    REGISTRY_PATH,
    ROOT,
    validate_interfaces,
)


def _load(relative: Path) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_capability_interface_registry_is_complete_and_valid() -> None:
    errors, summary = validate_interfaces(ROOT)

    assert errors == []
    assert summary["ok"] is True
    assert summary["architecture_tag"] == "arch-map/v3.7"
    assert summary["construction_version"] == "3.7.0"
    assert summary["entries"] == summary["expected_edges"]
    assert summary["entries"] >= 80
    assert summary["relations"]["runtime_dependency"] > 0
    assert summary["relations"]["acceptance_target"] == 3


def test_registry_covers_every_construction_relationship_exactly_once() -> None:
    construction = _load(CONSTRUCTION_PATH)
    registry = _load(REGISTRY_PATH)

    expected = {
        ("runtime_dependency", plane["id"], target)
        for plane in construction["planes"]
        for target in plane["depends_on"]
    }
    expected |= {
        ("acceptance_target", plane["id"], target)
        for plane in construction["planes"]
        for target in plane.get("validates", [])
    }
    observed = {
        (entry["relation"], entry["source_plane"], entry["target_plane"])
        for entry in registry["entries"]
    }

    assert observed == expected
    assert len(registry["entries"]) == len(observed)


def test_registry_owners_and_zones_match_structural_blueprint() -> None:
    construction = _load(CONSTRUCTION_PATH)
    architecture = _load(ARCHITECTURE_PATH)
    registry = _load(REGISTRY_PATH)

    planes = {plane["id"]: plane for plane in construction["planes"]}
    placements = {
        item["plane"]: item
        for item in architecture["structural_blueprint"]["plane_placements"]
    }

    for entry in registry["entries"]:
        source = entry["source_plane"]
        target = entry["target_plane"]
        assert entry["source_owner"] == planes[source]["owner"]
        assert entry["target_owner"] == planes[target]["owner"]
        assert entry["source_zone"] == placements[source]["zone"]
        assert entry["target_zone"] == placements[target]["zone"]
        assert (ROOT / entry["source_owner"]).exists()
        assert (ROOT / entry["target_owner"]).exists()


def test_runtime_cross_zone_interfaces_follow_zone_dag() -> None:
    architecture = _load(ARCHITECTURE_PATH)
    registry = _load(REGISTRY_PATH)
    allowed = {
        zone["id"]: set(zone["may_depend_on"])
        for zone in architecture["zones"]
    }

    for entry in registry["entries"]:
        if entry["relation"] != "runtime_dependency":
            continue
        source_zone = entry["source_zone"]
        target_zone = entry["target_zone"]
        if source_zone == target_zone:
            assert entry["boundary"] == "intra-zone"
        else:
            assert target_zone in allowed[source_zone]
            assert entry["boundary"] == "cross-zone"


def test_acceptance_interfaces_are_evidence_only_and_exact() -> None:
    registry = _load(REGISTRY_PATH)
    acceptance = [
        entry
        for entry in registry["entries"]
        if entry["relation"] == "acceptance_target"
    ]

    assert {
        (entry["source_plane"], entry["target_plane"])
        for entry in acceptance
    } == {
        ("deployment-release", "application-api"),
        ("deployment-release", "engine-api"),
        ("deployment-release", "product-experience"),
    }
    assert all(entry["boundary"] == "evidence-only" for entry in acceptance)
    assert all(entry["binding"] == "evidence-contract" for entry in acceptance)


def test_model_routing_interface_owner_is_engine_canonical() -> None:
    registry = _load(REGISTRY_PATH)

    routing_edges = [
        entry
        for entry in registry["entries"]
        if entry["source_plane"] == "model-routing"
        or entry["target_plane"] == "model-routing"
    ]

    assert routing_edges
    for entry in routing_edges:
        if entry["source_plane"] == "model-routing":
            assert entry["source_owner"] == "skeleton/frontier/model_routing.py"
            assert entry["source_zone"] == "engine"
        if entry["target_plane"] == "model-routing":
            assert entry["target_owner"] == "skeleton/frontier/model_routing.py"
            assert entry["target_zone"] == "engine"


def test_interface_status_is_derived_from_connected_plane_maturity() -> None:
    construction = _load(CONSTRUCTION_PATH)
    registry = _load(REGISTRY_PATH)
    states = {plane["id"]: plane["state"] for plane in construction["planes"]}

    for entry in registry["entries"]:
        expected = (
            "partial"
            if "partial"
            in {
                states[entry["source_plane"]],
                states[entry["target_plane"]],
            }
            else "present"
        )
        assert entry["status"] == expected
