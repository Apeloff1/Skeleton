"""Regression coverage for TREE-014 Forge pipeline migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_pipeline_package_reexports_canonical_forge_package() -> None:
    legacy = importlib.import_module("skeleton.pipelines")
    canonical = importlib.import_module("skeleton.forge.pipelines")

    assert legacy.NPCPipeline is canonical.NPCPipeline
    assert legacy.GameLogicPipeline is canonical.GameLogicPipeline
    assert legacy.AnimationPipeline is canonical.AnimationPipeline
    assert legacy.GameForge is canonical.GameForge


def test_legacy_pipeline_modules_reexport_canonical_modules() -> None:
    pairs = (
        ("core", "PipelineRunner"),
        ("npc", "NpcPipeline"),
        ("speculative_rag", "SpeculativeRagBundle"),
    )
    for module_name, symbol in pairs:
        legacy = importlib.import_module(f"skeleton.pipelines.{module_name}")
        canonical = importlib.import_module(
            f"skeleton.forge.pipelines.{module_name}"
        )
        assert getattr(legacy, symbol) is getattr(canonical, symbol)


def test_ai_tree_forge_mapping_no_longer_excludes_pipelines() -> None:
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    forge = next(item for item in manifest["mappings"] if item["id"] == "AIFT-FORGE")
    pipelines = next(
        item for item in manifest["mappings"] if item["id"] == "AIFT-PIPELINES"
    )

    assert "pipelines" not in forge.get("overlay_children", [])
    assert pipelines["source"] == "skeleton/forge/pipelines"
    assert pipelines["destination"] == "skeleton/ai/forge/pipelines"
