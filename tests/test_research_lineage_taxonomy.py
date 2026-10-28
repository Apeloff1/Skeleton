"""Regression coverage for TREE-031 research-lineage taxonomy convergence."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _taxonomy() -> dict:
    with (ROOT / ".machine" / "repository.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_research_lineage_roots_are_historical_not_runtime_support() -> None:
    taxonomy = _taxonomy()
    zones = {zone["name"]: zone for zone in taxonomy["zone"]}
    research = zones["research-lineage"]
    specialized = zones["specialized-runtime"]

    assert research["lifecycle"] == "historical"
    assert research["owner"] == "ai-runtime"
    assert set(research["prefixes"]) == {
        "skeleton/circulation/",
        "skeleton/hoag/",
        "skeleton/motive/",
        "skeleton/sheaf/",
        "skeleton/spine/",
        "skeleton/viscera/",
    }
    # Preserve the explicit (not catch-all) owner inventory for live roots.
    # These nine roots are separately classified as unresolved, not promoted
    # to the historical research-lineage lifecycle.
    assert set(specialized["prefixes"]) == {
        "skeleton/cue/",
        "skeleton/cs300/",
        "skeleton/dna/",
        "skeleton/fix/",
        "skeleton/house/",
        "skeleton/maximise/",
        "skeleton/organs/",
        "skeleton/p3/",
        "skeleton/p4/",
        "skeleton/p5/",
        "skeleton/genos/",
        "skeleton/parse/",
        "skeleton/turn/",
    }
    assert set(research["prefixes"]).isdisjoint(specialized["prefixes"])


def test_tree031_records_taxonomy_only_classification() -> None:
    plan = json.loads((ROOT / "machine" / "repository_migration_plan.json").read_text(encoding="utf-8"))
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-031")

    assert batch["mode"] == "taxonomy-classification"
    assert batch["state"] == "classified"
    assert batch["destination"] == ".machine/repository.toml research-lineage zone"
