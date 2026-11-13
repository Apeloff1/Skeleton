"""Shortest faction ending witnesses and bounded-search safety."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import demo_actions
from skeleton.game.gameplay.quest_factions import (
    original_factions, simulate_factions,
)
from skeleton.game.gameplay.quest_factions_route import (
    cli, plan_factions, verify_plan,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _checkpoint():
    return simulate_factions(original_factions(), demo_actions()[:-1])


def test_plan_from_real_checkpoint_finishes_and_exports():
    saved = _checkpoint()
    plan = plan_factions(session=saved, target_ending="beacon_lit")
    assert plan["status"] == "found"
    assert plan["actions"] == [{"kind": "finish", "ending_id": "beacon_lit"}]
    final = verify_plan(json.loads(json.dumps(plan)), session=saved)
    assert final["state"]["standing"]["harbor_wardens"] == 4
    assert final["state"]["phase"] == "finished"


def test_faction_gate_prevents_unearned_finish():
    source = original_factions()
    source["ending_requirements"][0]["minimum_standing"][0]["minimum"] = 5
    saved = simulate_factions(source, demo_actions()[:-1])
    plan = plan_factions(session=saved, target_ending="beacon_lit",
                         max_states=1, max_depth=1)
    assert plan["status"] != "found"
    with pytest.raises(CombatSessionError, match="only found"):
        verify_plan(plan, session=saved)


def test_terminal_alternate_ending_not_misreported_as_target():
    saved = simulate_factions(original_factions(), demo_actions())
    plan = plan_factions(session=saved, target_ending="quiet_victory")
    assert plan["status"] == "unreachable"
    assert plan["actions"] == []


def test_search_limits_and_receipt_tamper_fail_closed():
    saved = _checkpoint()
    with pytest.raises(CombatSessionError, match="state budget"):
        plan_factions(session=saved, max_states=True)
    with pytest.raises(CombatSessionError, match="depth budget"):
        plan_factions(session=saved, max_depth=100)
    plan = plan_factions(session=saved)
    bad = copy.deepcopy(plan)
    bad["portable_checksum"] = "0" * 64
    with pytest.raises(CombatSessionError, match="search receipt mismatch"):
        verify_plan(bad, session=saved)


def test_cli_main_dispatch_from_checkpoint(capsys):
    from skeleton.__main__ import main
    saved = _checkpoint()
    assert main(["quest-factions-route", "--session-json", json.dumps(saved)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "found"
    assert cli(["--session-json", json.dumps(saved),
                "--verify-json", json.dumps(plan)]) == 0
    assert json.loads(capsys.readouterr().out)["ending"] == "beacon_lit"
