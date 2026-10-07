from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.app.assembly import load_manifest
from skeleton.app.plan import build_plan, dependency_closure, validate_manifest_topology


def test_default_plan_is_dependency_closed_and_layered():
    manifest = load_manifest()
    plan = build_plan(manifest=manifest)

    assert plan.profile == "default"
    assert set(plan.requested) == set(manifest.default_services)
    assert set(plan.services) == set(manifest.default_services)
    assert plan.layers[0] == ("mongo",)
    assert plan.layers[1] == ("skeleton",)
    assert plan.layers[2] == ("backend",)
    assert plan.layers[-1] == ("frontend",)


def test_full_plan_contains_default_and_optional_services():
    manifest = load_manifest()
    default, full = validate_manifest_topology(manifest)

    assert set(default.services).issubset(full.services)
    assert "chroma" in full.services
    assert {"mongo", "chroma"}.issubset(full.layers[0])


def test_custom_plan_pulls_transitive_dependencies():
    manifest = load_manifest()

    plan = build_plan(manifest=manifest, requested=("frontend",))

    assert plan.profile == "custom"
    assert plan.requested == ("frontend",)
    assert set(plan.services) == {"mongo", "backend", "skeleton", "frontend"}
    assert plan.services[-1] == "frontend"


def test_dependency_closure_rejects_unknown_service():
    manifest = load_manifest()

    with pytest.raises(ValueError, match="unknown services requested"):
        dependency_closure(manifest, ("frontend", "ghost"))


def test_plan_rejects_dependency_cycle():
    manifest = load_manifest()
    frontend = replace(manifest.service("frontend"), depends_on=("backend",))
    backend = replace(manifest.service("backend"), depends_on=("frontend",))
    services = tuple(
        frontend if service.name == "frontend"
        else backend if service.name == "backend"
        else service
        for service in manifest.services
    )
    cyclic = replace(
        manifest,
        default_services=("frontend",),
        full_services=("frontend",),
        services=services,
    )

    with pytest.raises(ValueError, match="dependency cycle"):
        build_plan(manifest=cyclic)


def test_plan_payload_is_json_serializable():
    payload = build_plan().to_dict()
    encoded = json.dumps(payload, sort_keys=True)

    assert '"profile": "default"' in encoded
    assert '"frontend"' in encoded
    assert '"layers"' in encoded


def test_cli_plan_json_exposes_dependency_layers(capsys):
    from skeleton.app.cli import run_app_cli

    exit_code = run_app_cli(["plan", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["profile"] == "default"
    assert payload["layers"][0] == ["mongo"]
    assert payload["layers"][-1] == ["frontend"]


def test_structural_preflight_includes_topology_verdict():
    from pathlib import Path

    from skeleton.app.assembly import find_repo_root, preflight

    root = find_repo_root(Path(__file__))
    checks = preflight(root)
    topology = [check for check in checks if check.code == "topology:graph"]

    assert len(topology) == 1
    assert topology[0].ok is True
    assert "default=" in topology[0].message
    assert "full=" in topology[0].message


def test_compose_up_consumes_the_same_planned_order():
    from skeleton.app.assembly import compose_command

    plan = build_plan()
    command = compose_command("up", build=False)

    assert command[-len(plan.services):] == plan.services


def test_compose_profiles_are_derived_from_manifest_services():
    from dataclasses import replace

    from skeleton.app.assembly import compose_command

    manifest = load_manifest()
    chroma = replace(manifest.service("chroma"), profile="vector")
    services = tuple(
        chroma if service.name == "chroma" else service
        for service in manifest.services
    )
    customized = replace(manifest, services=services)

    command = compose_command("up", manifest=customized, full=True, build=False)

    assert "--profile" in command
    profile_index = command.index("--profile")
    assert command[profile_index + 1] == "vector"
    assert "full" not in command[: profile_index + 2]
