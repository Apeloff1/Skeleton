"""Regression coverage for TREE-015 Forge creator migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_creator_package_reexports_canonical_forge_creator() -> None:
    legacy = importlib.import_module("skeleton.creator")
    canonical = importlib.import_module("skeleton.forge.creator")

    assert legacy.IntentCompiler is canonical.IntentCompiler
    assert legacy.DesignPlan is canonical.DesignPlan
    assert legacy.compile_intent is canonical.compile_intent
    assert legacy.revert_edit is canonical.revert_edit


def test_legacy_creator_module_reexports_canonical_module() -> None:
    legacy = importlib.import_module("skeleton.creator.intent_compiler")
    canonical = importlib.import_module("skeleton.forge.creator.intent_compiler")

    assert legacy.IntentCompiler is canonical.IntentCompiler
    assert legacy.DesignEdit is canonical.DesignEdit
    assert legacy.apply_edit is canonical.apply_edit


def test_ai_tree_forge_is_overlay_free_after_creator_cutover() -> None:
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    forge = next(item for item in manifest["mappings"] if item["id"] == "AIFT-FORGE")
    creator = next(item for item in manifest["mappings"] if item["id"] == "AIFT-CREATOR")

    assert not forge.get("overlay_children")
    assert creator["source"] == "skeleton/forge/creator"
    assert creator["destination"] == "skeleton/ai/forge/creator"
