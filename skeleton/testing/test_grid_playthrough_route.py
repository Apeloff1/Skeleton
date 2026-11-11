"""End-to-end grid campaign movement, collision and replay route solver."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Session
from skeleton.game.gameplay.grid_playthrough_route import (
    SCHEMA, plan_playthrough, verify_playthrough,
)


def _source() -> Path:
    return Path(__file__).resolve().parents[1] / "game/gameplay/content/lantern_harbor.json"


def _campaign() -> Campaign:
    return Campaign.load(json.loads(_source().read_text(encoding="utf-8")))


@pytest.mark.parametrize("ending", ["homecoming", "wanderer", "bright-harbor"])
def test_original_endings_have_replayable_player_paths(ending: str) -> None:
    campaign = _campaign()
    report = plan_playthrough(campaign, ending)
    assert report["schema_version"] == SCHEMA
    assert report["status"] == "solved"
    assert report["commands"]
    saved = Session.restore(campaign, report["save"])
    assert saved.ending == ending
    assert saved.state_digest == report["state_digest"]
    assert verify_playthrough(campaign, json.loads(json.dumps(report))) == report


def test_search_is_stable_across_source_json_order() -> None:
    campaign = _campaign()
    source = campaign.spec
    source["objects"].reverse()
    first = plan_playthrough(campaign, "homecoming")
    # Source identity differs after reordered authored objects, but outcome
    # and canonical command sequence must remain equivalent.
    second = plan_playthrough(Campaign.load(source), "homecoming")
    assert [(x["kind"], x["target"]) for x in first["commands"]] == [
        (x["kind"], x["target"]) for x in second["commands"]
    ]


def test_budget_exhaustion_is_not_a_false_unreachable_claim() -> None:
    result = plan_playthrough(_campaign(), "homecoming", max_nodes=1)
    assert result["status"] == "inconclusive"
    assert result["save"] is None
    assert verify_playthrough(_campaign(), result) == result


@pytest.mark.parametrize("field,value", [
    ("max_nodes", 0), ("max_nodes", True), ("max_nodes", 4097),
    ("max_depth", 0), ("max_depth", 129), ("max_depth", 1.5),
])
def test_invalid_budgets_denied(field, value) -> None:
    with pytest.raises(GameplayContractError):
        plan_playthrough(_campaign(), "homecoming", **{field: value})


def test_unknown_ending_denied() -> None:
    with pytest.raises(GameplayContractError):
        plan_playthrough(_campaign(), "not-authored")


@pytest.mark.parametrize("key,value", [
    ("checksum", "0" * 64),
    ("status", "unreachable"),
    ("goal_ending", "wanderer"),
    ("commands", []),
    ("state_digest", "0" * 64),
])
def test_forged_route_receipts_denied(key, value) -> None:
    campaign = _campaign()
    report = plan_playthrough(campaign, "homecoming")
    report[key] = value
    with pytest.raises(GameplayContractError):
        verify_playthrough(campaign, report)


def test_cli_solve_with_original_content() -> None:
    run = subprocess.run([
        sys.executable, "-m", "scripts.game.offline_grid_campaign",
        "solve", "--goal-ending", "homecoming", "--max-nodes", "1024",
    ], capture_output=True, text=True, check=False, timeout=25)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["status"] == "solved"
    assert verify_playthrough(_campaign(), report) == report
