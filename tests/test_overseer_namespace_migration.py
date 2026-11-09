from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_overseer_package_exports_are_canonical_identities() -> None:
    import skeleton.automation.overseer as canonical
    import skeleton.overseer as legacy
    assert legacy.OverseerEngine is canonical.OverseerEngine
    assert legacy.OverseerEngineV3 is canonical.OverseerEngineV3
    assert legacy.OverseerEngineV35 is canonical.OverseerEngineV35


@pytest.mark.parametrize(
    "module_name",
    ["control", "engine", "engine_v2", "engine_v3", "engine_v35", "governor", "twin"],
)
def test_overseer_module_shims_cover_canonical_exports(module_name: str) -> None:
    canonical = importlib.import_module(f"skeleton.automation.overseer.{module_name}")
    legacy = importlib.import_module(f"skeleton.overseer.{module_name}")
    exported = tuple(getattr(canonical, "__all__", tuple(name for name in vars(canonical) if not name.startswith("_"))))
    assert exported
    assert all(hasattr(legacy, name) for name in exported)


def test_canonical_overseer_source_does_not_import_legacy_namespace() -> None:
    root = Path(__file__).resolve().parents[1] / "skeleton" / "automation" / "overseer"
    assert [
        p.name for p in root.glob("*.py")
        if "skeleton.overseer." in p.read_text(encoding="utf-8")
    ] == []
