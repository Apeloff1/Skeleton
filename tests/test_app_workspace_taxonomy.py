"""Regression coverage for TREE-032 application workspace taxonomy."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _zones() -> list[dict]:
    with (ROOT / ".machine" / "repository.toml").open("rb") as fh:
        return tomllib.load(fh)["zone"]


def test_jeeves_app_has_specific_owner_before_generic_apps_zone() -> None:
    zones = _zones()
    by_name = {zone["name"]: zone for zone in zones}
    names = [zone["name"] for zone in zones]

    jeeves = by_name["jeeves-app"]
    apps = by_name["application-workspaces"]

    assert jeeves["prefixes"] == ["apps/jeeves/"]
    assert jeeves["owner"] == "jeeves-runtime"
    assert jeeves["lifecycle"] == "support"
    assert apps["prefixes"] == ["apps/"]
    assert apps["owner"] == "application-runtime"
    assert apps["lifecycle"] == "support"
    assert names.index("jeeves-app") < names.index("application-workspaces")


def test_tree032_records_apps_taxonomy_classification() -> None:
    plan = json.loads((ROOT / "machine" / "repository_migration_plan.json").read_text(encoding="utf-8"))
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-032")

    assert batch["source"] == "apps/"
    assert batch["mode"] == "taxonomy-classification"
    assert batch["state"] == "classified"
    assert plan["batches"][-1]["id"] == "TREE-032"
