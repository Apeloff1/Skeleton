"""Regression coverage for TREE-023 simulation-economy migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_economy_package_reexports_canonical_simulation_economy() -> None:
    legacy = importlib.import_module("skeleton.economy")
    canonical = importlib.import_module("skeleton.simulation.economy")

    assert legacy.Harbor is canonical.Harbor
    assert legacy.capabilities is canonical.capabilities
    assert legacy.PACKET == canonical.PACKET
    assert legacy.VERSION == canonical.VERSION


def test_legacy_economy_modules_reexport_canonical_modules() -> None:
    pairs = (
        ("harbor", "Harbor"),
        ("treasury", "Treasury"),
        ("capabilities", "capabilities"),
    )
    for module_name, symbol in pairs:
        legacy = importlib.import_module(f"skeleton.economy.{module_name}")
        canonical = importlib.import_module(
            f"skeleton.simulation.economy.{module_name}"
        )
        assert getattr(legacy, symbol) is getattr(canonical, symbol)


def test_ai_tree_simulation_no_longer_excludes_economy() -> None:
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    simulation = next(
        item for item in manifest["mappings"] if item["id"] == "AIFT-SIMULATION"
    )
    economy = next(
        item for item in manifest["mappings"] if item["id"] == "AIFT-ECONOMY"
    )

    assert "economy" not in simulation.get("overlay_children", [])
    assert economy["source"] == "skeleton/simulation/economy"
    assert economy["destination"] == "skeleton/ai/simulation/economy"


def test_tree_023_is_recorded_as_canonicalized() -> None:
    plan = json.loads(
        (ROOT / "machine/repository_migration_plan.json").read_text(
            encoding="utf-8"
        )
    )
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-023")

    assert batch["state"] == "canonicalized"
    assert batch["destination"] == "skeleton/simulation/economy/"
