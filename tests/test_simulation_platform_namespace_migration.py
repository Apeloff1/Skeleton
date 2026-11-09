"""Regression coverage for TREE-013 simulation-platform migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_platform_package_reexports_canonical_simulation_platform() -> None:
    legacy = importlib.import_module("skeleton.platform")
    canonical = importlib.import_module("skeleton.simulation.platform")

    assert legacy.GodotAdapter is canonical.GodotAdapter
    assert legacy.GodotAdapterError is canonical.GodotAdapterError
    assert legacy.materialise_pack is canonical.materialise_pack
    assert legacy.project_document is canonical.project_document


def test_legacy_godot_adapter_reexports_canonical_module() -> None:
    legacy = importlib.import_module("skeleton.platform.godot_adapter")
    canonical = importlib.import_module("skeleton.simulation.platform.godot_adapter")

    assert legacy.GodotAdapter is canonical.GodotAdapter
    assert legacy.adapt_document is canonical.adapt_document
    assert legacy.inventory_godot_footprint is canonical.inventory_godot_footprint


def test_ai_tree_simulation_mapping_no_longer_excludes_platform() -> None:
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    mapping = next(item for item in manifest["mappings"] if item["id"] == "AIFT-SIMULATION")
    platform = next(item for item in manifest["mappings"] if item["id"] == "AIFT-PLATFORM")

    assert "platform" not in mapping.get("overlay_children", [])
    assert platform["source"] == "skeleton/simulation/platform"
    assert platform["destination"] == "skeleton/ai/simulation/platform"
