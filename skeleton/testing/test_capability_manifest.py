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
