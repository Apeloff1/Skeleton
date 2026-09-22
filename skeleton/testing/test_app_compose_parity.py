from __future__ import annotations

from copy import deepcopy
import json
from importlib import resources

from scripts.check_app_compose_parity import parity_errors


def _manifest() -> dict[str, object]:
    return json.loads(
        resources.files("skeleton.app").joinpath("manifest.json").read_text(encoding="utf-8")
    )


def _compose_model_from_manifest(manifest: dict[str, object]) -> dict[str, object]:
    services: dict[str, object] = {}
    for item in manifest["services"]:
        assert isinstance(item, dict)
        name = item["name"]
        assert isinstance(name, str)
        depends_on = item.get("depends_on", [])
        assert isinstance(depends_on, list)
        service: dict[str, object] = {
            "depends_on": {
                dependency: {"condition": "service_started", "required": True}
                for dependency in depends_on
            }
        }
        profile = item.get("profile")
        if isinstance(profile, str) and profile:
            service["profiles"] = [profile]
        services[name] = service
    return {"services": services}


def test_compose_topology_matches_manifest_contract() -> None:
    manifest = _manifest()
    compose_model = _compose_model_from_manifest(manifest)

    assert parity_errors(manifest, compose_model) == []


def test_compose_only_dependency_edge_is_rejected() -> None:
    manifest = _manifest()
    compose_model = _compose_model_from_manifest(manifest)
    backend = compose_model["services"]["backend"]
    backend["depends_on"]["skeleton"] = {
        "condition": "service_started",
        "required": True,
    }

    errors = parity_errors(manifest, compose_model)

    assert errors == [
        "backend: depends_on drift: manifest=['mongo'] compose=['mongo', 'skeleton']"
    ]


def test_missing_compose_dependency_edge_is_rejected() -> None:
    manifest = _manifest()
    compose_model = _compose_model_from_manifest(manifest)
    frontend = compose_model["services"]["frontend"]
    del frontend["depends_on"]["skeleton"]

    errors = parity_errors(manifest, compose_model)

    assert errors == [
        "frontend: depends_on drift: manifest=['backend', 'skeleton'] compose=['backend']"
    ]


def test_compose_profile_drift_is_rejected() -> None:
    manifest = _manifest()
    compose_model = _compose_model_from_manifest(manifest)
    compose_model["services"]["chroma"]["profiles"] = ["vector"]

    errors = parity_errors(manifest, compose_model)

    assert errors == [
        "chroma: profile drift: manifest=['full'] compose=['vector']"
    ]


def test_compose_only_cycle_edge_cannot_bypass_manifest_planner() -> None:
    manifest = _manifest()
    compose_model = _compose_model_from_manifest(manifest)
    backend = compose_model["services"]["backend"]
    backend["depends_on"]["frontend"] = {
        "condition": "service_started",
        "required": True,
    }

    errors = parity_errors(manifest, compose_model)

    assert errors
    assert "backend: depends_on drift" in errors[0]


def test_service_set_drift_is_rejected() -> None:
    manifest = _manifest()
    compose_model = _compose_model_from_manifest(manifest)
    drifted = deepcopy(compose_model)
    del drifted["services"]["chroma"]
    drifted["services"]["ghost"] = {"depends_on": {}}

    errors = parity_errors(manifest, drifted)

    assert "compose is missing manifest services: ['chroma']" in errors
    assert "compose has services absent from manifest: ['ghost']" in errors
