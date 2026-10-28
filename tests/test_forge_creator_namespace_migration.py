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


def test_ai_tree_forge_creator_cutover_preserves_independent_native_owners() -> None:
    """Creator has a separate canonical mapping; Forge-native overlays remain governed."""
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    forge = next(item for item in manifest["mappings"] if item["id"] == "AIFT-FORGE")
    creator = next(item for item in manifest["mappings"] if item["id"] == "AIFT-CREATOR")

    assert forge["source"] == "skeleton/forge"
    assert forge["destination"] == "skeleton/ai/forge"
    assert creator["source"] == "skeleton/forge/creator"
    assert creator["destination"] == "skeleton/ai/forge/creator"

    overlays = forge.get("overlay_children", [])
    assert len(overlays) == len(set(overlays))
    assert "creator" not in overlays
    assert not any(path.startswith("creator/") for path in overlays)

    # The 25 Forge-native files are intentionally absent from the staged
    # legacy mirror. Every one must have its own non-residual canonical owner.
    native = {
        owner["path"].removeprefix("skeleton/ai/forge/")
        for owner in manifest["native_ai_owners"]
        if owner["path"].startswith("skeleton/ai/forge/")
        and owner.get("ownership_mode") == "canonical_native"
        and owner.get("residual_only") is False
    }
    assert native
    assert set(overlays) == native
    for relative in overlays:
        assert (ROOT / forge["destination"] / relative).is_file()
        assert not (ROOT / forge["source"] / relative).exists()
