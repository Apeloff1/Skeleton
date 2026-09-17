"""Regression coverage for stable Skeleton capability discovery and loading."""

from __future__ import annotations

import importlib
import importlib.util
import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITIES_BY_ID,
    CAPABILITY_MANIFEST_VERSION,
    CapabilityLoadError,
    CapabilityLoader,
    capability_lifecycle_snapshot,
    capability_manifest,
    capability_runtime_status,
    get_capability,
    load_capability,
)


def test_capability_manifest_is_versioned_unique_and_resolvable() -> None:
    payload = capability_manifest()

    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1

    capabilities = payload["capabilities"]
    assert isinstance(capabilities, list)
    assert capabilities

    ids = [capability["id"] for capability in capabilities]
    modules = [capability["module"] for capability in capabilities]

    assert len(ids) == len(set(ids))
    assert len(modules) == len(set(modules))
    assert {"gameforge", "cortex", "jeeves", "organism", "social", "galaxy"} <= set(ids)
    assert {
        "kernel",
        "memory",
        "intelligence",
        "swarm",
        "retrieval",
        "pipelines",
        "vault",
        "agents",
        "context",
        "resilience",
        "observability",
        "api",
        "developer",
        "deploy",
        "testing",
        "config",
        "content",
    } <= set(ids)

    for capability in capabilities:
        assert set(capability) == {"id", "module", "description"}
        assert capability["id"]
        assert capability["description"]
        assert importlib.util.find_spec(capability["module"]) is not None


def test_capability_lookup_is_stable_normalized_and_immutable() -> None:
    gameforge = get_capability("  GameForge  ")
    assert gameforge.id == "gameforge"
    assert CAPABILITIES_BY_ID["gameforge"] is gameforge

    with pytest.raises(KeyError, match="unknown capability: missing"):
        get_capability("missing")
    with pytest.raises(ValueError, match="must not be empty"):
        get_capability("   ")
    with pytest.raises(TypeError, match="must be a string"):
        get_capability(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        CAPABILITIES_BY_ID["missing"] = gameforge  # type: ignore[index]


def test_capability_loader_is_lazy_cached_and_manifest_bound(monkeypatch) -> None:
    calls: list[str] = []
    real_import = importlib.import_module

    def counting_import(module_name: str):
        calls.append(module_name)
        return real_import(module_name)

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        counting_import,
    )
    loader = CapabilityLoader()

    assert not any(status.loaded for status in loader.status())
    application = loader.resolve("  Application ")
    assert loader.resolve("application") is application
    assert application.__name__ == "skeleton.application"
    assert calls == ["skeleton.application"]
    assert loader.loaded_ids() == ("application",)
    assert loader.is_loaded("APPLICATION")

    statuses = {status.id: status for status in loader.status()}
    assert statuses["application"].loaded is True
    assert statuses["cortex"].loaded is False

    loader.clear_cache()
    assert loader.loaded_ids() == ()
    assert not loader.is_loaded("application")


def test_capability_loader_rejects_arbitrary_imports_before_import(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("unexpected import")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    loader = CapabilityLoader()

    with pytest.raises(KeyError, match="unknown capability: os"):
        loader.resolve("os")
    assert called is False


def test_capability_loader_redacts_import_failure_details(monkeypatch) -> None:
    def broken_import(_module_name: str):
        raise RuntimeError("sensitive import backend detail")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        broken_import,
    )
    loader = CapabilityLoader()

    with pytest.raises(CapabilityLoadError, match="failed to load capability: application") as exc_info:
        loader.resolve("application")

    assert "sensitive" not in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert loader.loaded_ids() == ()


def test_shared_capability_runtime_bridge_tracks_resolved_plane() -> None:
    application = load_capability("application")
    assert application.__name__ == "skeleton.application"

    statuses = {status.id: status for status in capability_runtime_status()}
    assert statuses["application"].loaded is True


def test_capabilities_cli_matches_python_api(capsys) -> None:
    assert main(["capabilities"]) == 0

    stdout = capsys.readouterr().out
    assert json.loads(stdout) == capability_manifest()


def test_capabilities_cli_lifecycle_matches_runtime_snapshot(capsys) -> None:
    from skeleton.application import CAPABILITY_LOADER

    CAPABILITY_LOADER.clear_cache()
    assert main(["capabilities", "--lifecycle"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == capability_lifecycle_snapshot()
    assert payload["kind"] == "lifecycle"
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION
    for capability in payload["capabilities"]:
        assert set(capability) == {"id", "module", "description", "resolvable", "loaded"}
        assert capability["resolvable"] is True
        assert capability["loaded"] is False


def test_capabilities_cli_rejects_unknown_options(capsys) -> None:
    assert main(["capabilities", "--dump"]) == 2
    assert "Unknown capabilities option" in capsys.readouterr().out


def test_lifecycle_snapshot_does_not_import_planes(monkeypatch) -> None:
    from skeleton.application import CAPABILITY_LOADER

    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("lifecycle must not import capability modules")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    CAPABILITY_LOADER.clear_cache()

    payload = capability_lifecycle_snapshot()
    assert called is False
    assert payload["kind"] == "lifecycle"
    assert all(row["loaded"] is False for row in payload["capabilities"])


def test_http_application_capability_routes_match_cli_payloads() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    assert asyncio.run(routes.application_capabilities()) == capability_manifest()
    assert asyncio.run(routes.application_capability_lifecycle()) == capability_lifecycle_snapshot()

    cortex = asyncio.run(routes.application_capability(" Cortex "))
    assert cortex["id"] == "cortex"
    assert cortex["module"] == "skeleton.cortex"

    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_capability("missing"))
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as empty:
        asyncio.run(routes.application_capability("   "))
    assert empty.value.status_code == 422


def test_shared_command_capabilities_matches_identity_manifest() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    result = service.execute("capabilities")
    assert result.ok is True
    assert result.to_payload()["data"] == capability_manifest()

    lifecycle = service.execute("capabilities", {"lifecycle": True})
    assert lifecycle.ok is True
    assert lifecycle.to_payload()["data"] == capability_lifecycle_snapshot()

    invalid = service.execute("capabilities", {"lifecycle": "yes"})
    assert invalid.ok is False
    assert invalid.to_payload()["error"]["code"] == "invalid_argument"
