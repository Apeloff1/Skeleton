"""Regression coverage for TREE-032 Turn compatibility taxonomy."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _zones() -> dict[str, dict]:
    with (ROOT / ".machine" / "repository.toml").open("rb") as fh:
        data = tomllib.load(fh)
    return {zone["name"]: zone for zone in data["zone"]}


def test_turn_is_transitional_compat_not_generic_specialized_runtime() -> None:
    zones = _zones()
    turn = zones["turn-compat"]
    specialized = zones["specialized-runtime"]

    assert turn["prefixes"] == ["skeleton/turn/"]
    assert turn["owner"] == "ai-runtime"
    assert turn["lifecycle"] == "transitional"
    assert "skeleton/turn/" not in specialized["prefixes"]
    assert set(specialized["prefixes"]) == {
        "skeleton/cue/",
        "skeleton/genos/",
        "skeleton/parse/",
    }


def test_tree032_records_turn_taxonomy_classification() -> None:
    plan = json.loads((ROOT / "machine" / "repository_migration_plan.json").read_text(encoding="utf-8"))
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-032")

    assert batch["mode"] == "taxonomy-classification"
    assert batch["state"] == "classified"
    assert batch["compatibility"] == "skeleton/turn/"
    assert plan["batches"][-1]["id"] == "TREE-032"
