"""Regression coverage for TREE-022 simulation-content migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_content_package_reexports_canonical_simulation_content() -> None:
    legacy = importlib.import_module("skeleton.content")
    canonical = importlib.import_module("skeleton.simulation.content")

    assert legacy.LOREBUFFA_AI_PACK is canonical.LOREBUFFA_AI_PACK
    assert legacy.get_npc_context is canonical.get_npc_context


def test_legacy_lorebuffa_module_reexports_canonical_module() -> None:
    legacy = importlib.import_module("skeleton.content.lorebuffa")
    canonical = importlib.import_module("skeleton.simulation.content.lorebuffa")

    assert legacy.LOREBUFFA_AI_PACK is canonical.LOREBUFFA_AI_PACK
    assert legacy.get_npc_context is canonical.get_npc_context


def test_ai_tree_simulation_no_longer_excludes_content() -> None:
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    simulation = next(
        item for item in manifest["mappings"] if item["id"] == "AIFT-SIMULATION"
    )
    content = next(
        item for item in manifest["mappings"] if item["id"] == "AIFT-CONTENT"
    )

    assert "content" not in simulation.get("overlay_children", [])
    assert content["source"] == "skeleton/simulation/content"
    assert content["destination"] == "skeleton/ai/simulation/content"


def test_tree_022_is_recorded_as_canonicalized() -> None:
    plan = json.loads(
        (ROOT / "machine/repository_migration_plan.json").read_text(
            encoding="utf-8"
        )
    )
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-022")

    assert batch["state"] == "canonicalized"
    assert batch["destination"] == "skeleton/simulation/content/"
