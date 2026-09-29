"""Regression coverage for TREE-033 runtime ownership refinement."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _zones() -> dict[str, dict]:
    with (ROOT / ".machine" / "repository.toml").open("rb") as fh:
        return {zone["name"]: zone for zone in tomllib.load(fh)["zone"]}


def test_simulation_zone_only_owns_actual_simulation_surfaces() -> None:
    zones = _zones()
    simulation = zones["simulation"]

    assert simulation["prefixes"] == ["skeleton/simulation/", "godot.pointer"]
    for misplaced in (
        "skeleton/era/",
        "skeleton/galaxy/",
        "skeleton/organism/",
        "skeleton/social/",
    ):
        assert misplaced not in simulation["prefixes"]


def test_specialized_roots_follow_their_documented_runtime_roles() -> None:
    zones = _zones()

    galaxy = zones["distributed-runtime"]
    assert galaxy["prefixes"] == ["skeleton/galaxy/"]
    assert galaxy["owner"] == "ai-runtime"
    assert galaxy["lifecycle"] == "canonical"

    organism = zones["organism-runtime"]
    assert organism["prefixes"] == ["skeleton/organism/"]
    assert organism["owner"] == "core-runtime"
    assert organism["lifecycle"] == "support"

    social = zones["social-research-intake"]
    assert social["prefixes"] == ["skeleton/social/"]
    assert social["owner"] == "ai-runtime"
    assert social["lifecycle"] == "transitional"

    era = zones["era-lineage"]
    assert era["prefixes"] == ["skeleton/era/"]
    assert era["owner"] == "core-runtime"
    assert era["lifecycle"] == "historical"


def test_tree033_records_taxonomy_only_refinement() -> None:
    plan = json.loads((ROOT / "machine" / "repository_migration_plan.json").read_text(encoding="utf-8"))
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-033")

    assert batch["mode"] == "taxonomy-classification"
    assert batch["state"] == "classified"
    assert plan["batches"][-1]["id"] == "TREE-033"
