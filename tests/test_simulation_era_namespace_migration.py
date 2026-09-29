"""Regression coverage for TREE-030 simulation-era migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_era_modules_reexport_canonical_runtime() -> None:
    legacy = importlib.import_module("skeleton.era")
    canonical = importlib.import_module("skeleton.simulation.era")

    assert legacy.EraBind is canonical.EraBind
    assert legacy.GameForgeRun is canonical.GameForgeRun
    assert legacy.capabilities is canonical.capabilities
    assert legacy.HOUSE_ERA == canonical.HOUSE_ERA


def test_canonical_and_ai_era_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/simulation/era", "skeleton/ai/simulation/era"):
        for path in (ROOT / relative).glob("*.py"):
            assert "skeleton.era" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_governs_canonical_era_and_preserves_parent_parity() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    simulation = next(item for item in manifest["mappings"] if item["id"] == "AIFT-SIMULATION")
    era = next(item for item in manifest["mappings"] if item["id"] == "AIFT-ERA")

    assert era["source"] == "skeleton/simulation/era"
    assert era["destination"] == "skeleton/ai/simulation/era"
    assert era["source_git_object_sha"] == "b3f65097f5347feedf00308bc06b89ed61f0f6a1"
    assert simulation["source_git_object_sha"] == "a9f8fbe017177927ac3125d1830031634a5cf85f"


def test_era_migration_follows_game_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    ids = [item["id"] for item in plan["batches"]]
    assert ids[-2:] == ["TREE-029", "TREE-030"]
