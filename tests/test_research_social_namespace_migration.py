"""Regression coverage for TREE-031 research-social migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_social_package_reexports_canonical_research_surface() -> None:
    legacy = importlib.import_module("skeleton.social")
    canonical = importlib.import_module("skeleton.research.social")

    assert legacy.SocialGraph is canonical.SocialGraph
    assert legacy.ReputationEngine is canonical.ReputationEngine
    assert legacy.InteractionLog is canonical.InteractionLog
    assert legacy.Interaction is canonical.Interaction


def test_canonical_and_ai_social_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/research/social", "skeleton/ai/research/social"):
        for path in (ROOT / relative).glob("*.py"):
            assert "skeleton.social" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_retargets_social_to_canonical_research_owner() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    social = next(item for item in manifest["mappings"] if item["id"] == "AIFT-SOCIAL")

    assert social["source"] == "skeleton/research/social"
    assert social["destination"] == "skeleton/ai/research/social"
    assert social["source_git_object_sha"] == "8648d7d27f18e87620b1603d1adc4335a887d690"
    assert "skeleton/research" not in manifest["planned_path_audit"]["planned_but_absent"]


def test_social_migration_follows_era_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    ids = [item["id"] for item in plan["batches"]]
    assert ids[-2:] == ["TREE-030", "TREE-031"]
