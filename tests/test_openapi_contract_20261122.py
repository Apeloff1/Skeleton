"""The published engine OpenAPI contract must match the mounted routes.

``docs/api/openapi.v1.json`` is generated from ``skeleton.api.server.create_app``
by ``scripts/export_openapi.py``. This test regenerates it and compares the
operation surface (method, path, operationId, parameters, body presence), which
is stable across FastAPI patch releases, and runs the structural lint.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_openapi.py"


def _exporter():
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def exporter():
    return _exporter()


@pytest.fixture(scope="module")
def live(exporter):
    return exporter.generate()


def _surface(exporter, spec):
    rows = {}
    for method, path, operation in exporter.operations(spec):
        params = sorted(
            (str(p.get("in")), str(p.get("name")), bool(p.get("required")))
            for p in operation.get("parameters") or [] if isinstance(p, dict)
        )
        rows[(method, path)] = {
            "operationId": operation.get("operationId"),
            "parameters": params,
            "body": "requestBody" in operation,
            "statuses": sorted(operation.get("responses") or {}),
        }
    return rows


def test_live_spec_passes_structural_lint(exporter, live):
    assert exporter.lint(live) == []
    assert str(live["openapi"]).startswith("3.1")
    assert sum(1 for _ in exporter.operations(live)) > 100


def test_committed_snapshot_matches_mounted_operations(exporter, live):
    committed = json.loads(exporter.SNAPSHOT.read_text(encoding="utf-8"))
    expected = _surface(exporter, committed)
    actual = _surface(exporter, live)
    added = sorted(set(actual) - set(expected))
    removed = sorted(set(expected) - set(actual))
    changed = sorted(k for k in set(actual) & set(expected) if actual[k] != expected[k])
    assert not (added or removed or changed), (
        "docs/api/openapi.v1.json drifted; run python scripts/export_openapi.py\n"
        f"added={added[:20]} removed={removed[:20]} changed={changed[:20]}"
    )


def test_health_and_core_routes_are_published(live):
    paths = live["paths"]
    for path in ("/api/v1/health/live", "/api/v1/health/ready", "/api/v1/game/build"):
        assert path in paths, path


def test_lint_catches_contract_defects(exporter):
    broken = {
        "openapi": "3.0.0",
        "info": {"title": "x"},
        "paths": {
            "/a/{item_id}": {"get": {"operationId": "dup", "responses": {}}},
            "/b": {"post": {"operationId": "dup", "responses": {"200": {}}}},
            "/c": {"put": {"responses": {"200": {}}}},
        },
    }
    problems = "\n".join(exporter.lint(broken))
    assert "3.1" in problems
    assert "info.title and info.version" in problems
    assert "duplicate operationId 'dup'" in problems
    assert "no responses declared" in problems
    assert "path parameter 'item_id' is not declared" in problems
    assert "missing operationId" in problems


def test_generation_pins_surface_toggles(exporter, monkeypatch, live):
    monkeypatch.setenv("SKELETON_OMNIFABRIC_API", "0")
    pinned = exporter.generate()
    assert set(pinned["paths"]) == set(live["paths"])
    import os
    assert os.environ["SKELETON_OMNIFABRIC_API"] == "0"
