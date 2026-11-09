"""Regression coverage for TREE-019 Frontier economy extraction."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_flat_frontier_economy_modules_reexport_canonical_modules() -> None:
    pairs = (
        ("commerce", "ShopItemSpec"),
        ("cooking", "CookingRecipe"),
        ("cooking_adapters", "energy_booster_from_cooking_buff"),
        ("crafting", "CraftingRecipe"),
        ("crafting_adapters", "energy_booster_from_craft_output"),
        ("energy", "EnergyState"),
        ("energy_adapters", "energy_event"),
        ("equipment", "EquipmentSpec"),
    )
    for module_name, symbol in pairs:
        legacy = importlib.import_module(f"skeleton.frontier.{module_name}")
        canonical = importlib.import_module(
            f"skeleton.frontier.economy.{module_name}"
        )
        assert getattr(legacy, symbol) is getattr(canonical, symbol)


def test_frontier_ai_tree_records_economy_canonicalization() -> None:
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    frontier = next(
        item for item in manifest["mappings"] if item["id"] == "AIFT-FRONTIER"
    )

    assert frontier["source"] == "skeleton/frontier"
    assert frontier["destination"] == "skeleton/ai/runtime/frontier"
    assert "economy" in frontier["role"]
    assert "economy" in frontier["source_disposition"]


def test_tree_019_is_recorded_as_canonicalized() -> None:
    plan = json.loads(
        (ROOT / "machine/repository_migration_plan.json").read_text(
            encoding="utf-8"
        )
    )
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-019")

    assert batch["state"] == "canonicalized"
    assert batch["destination"] == "skeleton/frontier/economy/"
