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

    assert legacy_mechanics.CombatSystemSpec is canonical_mechanics.CombatSystemSpec
    assert legacy_mechanics.GameMechanicsGenerator is canonical_mechanics.GameMechanicsGenerator
    assert legacy_replay.ReplayTrace is canonical_replay.ReplayTrace


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
    assert "overlay_children" not in simulation


def test_game_migration_follows_agents_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    sources = [item["source"] for item in plan["batches"]]
    assert sources.index("skeleton/agents/") < sources.index("skeleton/game/")
    batch = next(item for item in plan["batches"] if item["source"] == "skeleton/game/")
    assert batch["state"] == "canonicalized"
