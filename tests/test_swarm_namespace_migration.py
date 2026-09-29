from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_swarm_package_exports_are_canonical_identities() -> None:
    import skeleton.automation.swarm as canonical
    import skeleton.swarm as legacy

    assert legacy.Mesh is canonical.Mesh
    assert legacy.SwarmDag is canonical.SwarmDag
    assert legacy.ReadyWaveRunner is canonical.ReadyWaveRunner


@pytest.mark.parametrize(
    "module_name",
    [
        "capabilities",
        "mesh",
        "mesh_handoff",
        "negotiation",
        "platoons",
        "ready_wave_runner",
        "roles",
        "stigmergy",
    ],
)
def test_swarm_module_shims_cover_canonical_exports(module_name: str) -> None:
    canonical = importlib.import_module(f"skeleton.automation.swarm.{module_name}")
    legacy = importlib.import_module(f"skeleton.swarm.{module_name}")
    exported = tuple(
        getattr(
            canonical,
            "__all__",
            tuple(name for name in vars(canonical) if not name.startswith("_")),
        )
    )
    assert exported
    assert all(hasattr(legacy, name) for name in exported)


def test_canonical_swarm_source_does_not_import_legacy_namespace() -> None:
    root = Path(__file__).resolve().parents[1] / "skeleton" / "automation" / "swarm"
    offenders = [
        path.name
        for path in root.glob("*.py")
        if "skeleton.swarm." in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
