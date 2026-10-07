from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_hive_package_exports_are_canonical_identities() -> None:
    import skeleton.automation.hive as canonical
    import skeleton.hive as legacy
    assert legacy.Hive is canonical.Hive
    assert legacy.HiveEngine is canonical.HiveEngine


@pytest.mark.parametrize("module_name", ["capabilities", "cards", "engine", "kernel", "verify"])
def test_hive_module_shims_cover_canonical_exports(module_name: str) -> None:
    canonical = importlib.import_module(f"skeleton.automation.hive.{module_name}")
    legacy = importlib.import_module(f"skeleton.hive.{module_name}")
    exported = tuple(getattr(canonical, "__all__", tuple(name for name in vars(canonical) if not name.startswith("_"))))
    assert exported
    assert all(hasattr(legacy, name) for name in exported)


def test_canonical_hive_source_does_not_import_legacy_namespace() -> None:
    root = Path(__file__).resolve().parents[1] / "skeleton" / "automation" / "hive"
    assert [
        p.name for p in root.glob("*.py")
        if "skeleton.hive." in p.read_text(encoding="utf-8")
    ] == []
