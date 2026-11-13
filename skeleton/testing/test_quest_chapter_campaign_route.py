"""Campaign completion routes must use earned quest and chapter actions."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.quest_chapter_campaign import (
    demo_campaign_actions, export_campaign, original_campaign,
    simulate_campaign,
)
from skeleton.game.gameplay.quest_chapter_campaign_route import (
    cli, plan_campaign, verify_campaign_plan,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def near_terminal():
    return simulate_campaign(
        original_campaign(), demo_campaign_actions()[:-2],
    )


def test_checkpoint_completes_last_chapter_and_exports_verified_campaign():
    start = near_terminal()
    plan = plan_campaign(session=start, max_states=16, max_depth=2)
    assert plan["status"] == "found"
    assert plan["actions"][-1] == {"kind": "advance"}
    assert len(plan["chapters"]) == 1
    assert plan["chapters"][0]["chapter_id"] == "night_watch"
    final = verify_campaign_plan(json.loads(json.dumps(plan)), session=start)
    assert final["state"]["phase"] == "won"
    assert plan["portable_checksum"] == export_campaign(final)["checksum"]
    assert final == simulate_campaign(original_campaign(), demo_campaign_actions())


def test_finished_checkpoint_is_already_completed_without_fake_actions():
    finished = simulate_campaign(original_campaign(), demo_campaign_actions())
    plan = plan_campaign(session=finished, max_states=4, max_depth=2)
    assert plan["status"] == "found"
    assert plan["actions"] == []
    assert plan["explored"] == 0
    assert verify_campaign_plan(plan, session=finished) == finished


def test_exhausted_route_is_inconclusive_not_a_victory():
    plan = plan_campaign(original_campaign(), max_states=1, max_depth=1)
    assert plan["status"] == "inconclusive"
    assert plan["budget_exhausted"] is True
    assert plan["portable_checksum"] is None
    with pytest.raises(CombatSessionError, match="found|completed"):
        verify_campaign_plan(plan, source=original_campaign())


@pytest.mark.parametrize("field,value", [
    ("source_digest", "0" * 64),
    ("final_state_digest", "0" * 64),
    ("portable_checksum", "0" * 64),
    ("explored", 999),
    ("max_states", 1),
    ("actions", []),
    ("chapters", []),
    ("checksum", "0" * 64),
])
def test_tampered_route_receipt_is_rejected_even_when_rechecks_replay(field, value):
    start = near_terminal()
    plan = plan_campaign(session=start, max_states=16, max_depth=2)
    forged = copy.deepcopy(plan)
    forged[field] = value
    if forged == plan:
        pytest.skip("mutation matches canonical receipt")
    with pytest.raises(CombatSessionError):
        verify_campaign_plan(forged, session=start)


@pytest.mark.parametrize("kwargs", [
    {"max_states": 0}, {"max_states": True}, {"max_states": 2049},
    {"max_depth": 0}, {"max_depth": True}, {"max_depth": 33},
])
def test_invalid_route_budgets_fail_closed(kwargs):
    with pytest.raises(CombatSessionError):
        plan_campaign(session=near_terminal(), **kwargs)


def test_wrong_source_and_untrusted_claims_do_not_verify():
    start = near_terminal()
    plan = plan_campaign(session=start, max_states=16, max_depth=2)
    with pytest.raises(CombatSessionError):
        verify_campaign_plan(plan, source=original_campaign())
    with pytest.raises(CombatSessionError):
        verify_campaign_plan({"schema_version": "v1"}, session=start)


def test_installed_cli_plans_and_verifies_exact_checkpoint(capsys):
    from skeleton.__main__ import main
    saved = near_terminal()
    args = ["--session-json", json.dumps(saved), "--max-states", "16",
            "--max-depth", "2"]
    assert main(["quest-campaign-route", *args]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "found"
    assert cli(["--session-json", json.dumps(saved),
                "--verify-json", json.dumps(plan)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["ok"] is True
    assert verified["portable_checksum"] == plan["portable_checksum"]


def test_cli_rejects_invalid_source(capsys):
    assert cli(["--source-json", '{"bad":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
