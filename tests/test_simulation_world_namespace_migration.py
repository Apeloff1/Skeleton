"""Regression coverage for TREE-027 simulation-world migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_world_package_reexports_canonical_simulation_world() -> None:
    legacy = importlib.import_module("skeleton.world")
    canonical = importlib.import_module("skeleton.simulation.world")

    assert legacy.WorldState is canonical.WorldState
    assert legacy.SceneEntity is canonical.SceneEntity
    assert legacy.Transform is canonical.Transform
    assert legacy.diagnose_payload is canonical.diagnose_payload


def test_legacy_world_scene_reexports_canonical_scene_module() -> None:
    legacy = importlib.import_module("skeleton.world.scene")
    canonical = importlib.import_module("skeleton.simulation.world.scene")

    assert legacy.WorldState is canonical.WorldState
    assert legacy.SceneEntity is canonical.SceneEntity


def test_ai_tree_simulation_has_no_remaining_overlay() -> None:
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    simulation = next(
        item for item in manifest["mappings"] if item["id"] == "AIFT-SIMULATION"
    )
    world = next(item for item in manifest["mappings"] if item["id"] == "AIFT-WORLD")

    assert simulation.get("overlay_children", []) == []
    assert world["source"] == "skeleton/simulation/world"
    assert world["destination"] == "skeleton/ai/simulation/world"


def test_world_migration_is_recorded_as_canonicalized() -> None:
    plan = json.loads(
        (ROOT / "machine/repository_migration_plan.json").read_text(
            encoding="utf-8"
        )
    )
    batch = next(
        item for item in plan["batches"]
        if item["source"] == "skeleton/world/"
        and item["destination"] == "skeleton/simulation/world/"
    )

    assert batch["id"] == "TREE-027"
    assert batch["state"] == "canonicalized"
