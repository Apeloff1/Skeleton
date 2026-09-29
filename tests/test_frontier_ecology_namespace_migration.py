"""Regression coverage for TREE-018 Frontier ecology extraction."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_flat_frontier_ecology_modules_reexport_canonical_modules() -> None:
    pairs = (
        ("aquarium", "AquariumState"),
        ("aquarium_adapters", "aquarium_state_payload"),
        ("bait", "BaitSpec"),
        ("biotope", "BiotopeProgress"),
        ("biotope_achievement_adapters", "empty_biotope_catch_evidence"),
        ("biotope_adapters", "biotope_progress_payload"),
        ("breeding", "BreedingJob"),
        ("breeding_adapters", "breeding_offspring_digest"),
    )
    for module_name, symbol in pairs:
        legacy = importlib.import_module(f"skeleton.frontier.{module_name}")
        canonical = importlib.import_module(
            f"skeleton.frontier.ecology.{module_name}"
        )
        assert getattr(legacy, symbol) is getattr(canonical, symbol)


def test_frontier_ai_tree_records_ecology_canonicalization() -> None:
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    frontier = next(
        item for item in manifest["mappings"] if item["id"] == "AIFT-FRONTIER"
    )

    assert frontier["source"] == "skeleton/frontier"
    assert frontier["destination"] == "skeleton/ai/runtime/frontier"
    assert "ecology" in frontier["role"]
    assert "ecology" in frontier["source_disposition"]


def test_tree_018_is_recorded_as_canonicalized() -> None:
    plan = json.loads(
        (ROOT / "machine/repository_migration_plan.json").read_text(
            encoding="utf-8"
        )
    )
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-018")

    assert batch["state"] == "canonicalized"
    assert batch["destination"] == "skeleton/frontier/ecology/"
