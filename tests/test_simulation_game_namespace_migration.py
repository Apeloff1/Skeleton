"""Regression coverage for TREE-029 simulation-game migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_game_modules_reexport_canonical_runtime() -> None:
    legacy_mechanics = importlib.import_module("skeleton.game.mechanics")
    canonical_mechanics = importlib.import_module("skeleton.simulation.game.mechanics")
    legacy_replay = importlib.import_module("skeleton.game.replay")
    canonical_replay = importlib.import_module("skeleton.simulation.game.replay")

    assert legacy_mechanics.MechanicSpec is canonical_mechanics.MechanicSpec
    assert legacy_replay.ReplayRecord is canonical_replay.ReplayRecord


def test_canonical_and_ai_game_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/simulation/game", "skeleton/ai/simulation/game"):
        for path in (ROOT / relative).rglob("*.py"):
            assert "skeleton.game" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_retargets_game_and_closes_simulation_overlay() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    simulation = next(item for item in manifest["mappings"] if item["id"] == "AIFT-SIMULATION")
    game = next(item for item in manifest["mappings"] if item["id"] == "AIFT-GAME")

    assert game["source"] == "skeleton/simulation/game"
    assert game["destination"] == "skeleton/ai/simulation/game"
    assert game["source_git_object_sha"] == "9abc5257e09e0bfafc2bee544483798b1280dd89"
    assert "overlay_children" not in simulation
    assert simulation["source_git_object_sha"] == "e109d865ed3f55e7b318ba9bb03611b287f434b0"


def test_game_migration_follows_agents_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    ids = [item["id"] for item in plan["batches"]]
    assert ids[-2:] == ["TREE-028", "TREE-029"]
