"""Gameplay decision previews execute real source-bound quest transitions."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import (
    demo_actions, new_quest, original_quest, simulate_quest,
)
from skeleton.game.gameplay.expedition_quest_decisions import (
    apply_decision, cli, preview_decisions, verify_decision,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_preview_is_deterministic_and_does_not_mutate_start():
    start = new_quest(original_quest())
    before = copy.deepcopy(start)
    preview = preview_decisions(session=start)
    assert start == before
    assert preview == preview_decisions(session=json.loads(json.dumps(start)))
    assert preview["initial_state_digest"] == start["state_digest"]
    assert preview["preview_count"] == preview["available_count"]
    assert preview["candidates"]
    assert all(item["status"] == "playable" for item in preview["candidates"])


def test_apply_real_earned_npc_choice_and_portable_replay():
    start = new_quest(original_quest())
    action = {"kind": "talk", "npc_id": "guide", "decision": "aid"}
    record = apply_decision(start, action, expected_state_digest=start["state_digest"])
    played = verify_decision(json.loads(json.dumps(record)))
    assert played["state"]["choices"]["guide"] == "aid"
    assert played["state"]["items"]["reed"] == 1
    assert played["state"]["tick"] == 1
    assert record["after_state_digest"] == played["state_digest"]


def test_declining_npc_does_not_grant_gift():
    start = new_quest(original_quest())
    record = apply_decision(
        start, {"kind": "talk", "npc_id": "guide", "decision": "decline"},
        expected_state_digest=start["state_digest"],
    )
    played = verify_decision(record)
    assert played["state"]["choices"] == {"guide": "decline"}
    assert played["state"]["items"] == {}


def test_preview_after_combat_and_crafting_matches_real_play():
    played = simulate_quest(original_quest(), demo_actions()[:6])
    preview = preview_decisions(session=played)
    combat = next(p for p in preview["candidates"]
                  if p["action"] == {"kind": "expedition", "action": {"kind": "fight"}})
    assert combat["status"] == "playable"
    assert combat["state"]["tick"] == 7
    assert combat["state"]["crafted"] == ["beacon"]
    assert combat["state"]["currency"] > 0
    record = apply_decision(
        played, combat["action"], expected_state_digest=played["state_digest"]
    )
    assert verify_decision(record)["state_digest"] == combat["state_digest"]


def test_truncated_preview_never_claims_full_coverage():
    start = new_quest(original_quest())
    report = preview_decisions(session=start, limit=1)
    assert report["preview_count"] == 1
    assert report["available_count"] >= 2
    assert report["truncated"] is True


@pytest.mark.parametrize("limit", [0, 25, True, 1.5, "2"])
def test_preview_budget_fail_closed(limit):
    with pytest.raises(CombatSessionError, match="limit"):
        preview_decisions(original_quest(), limit=limit)


def test_stale_digest_and_illegal_actions_fail_closed():
    start = new_quest(original_quest())
    with pytest.raises(CombatSessionError, match="stale"):
        apply_decision(start, {"kind": "wait"}, expected_state_digest="0" * 64)
    with pytest.raises(CombatSessionError, match="legal"):
        apply_decision(start, {"kind": "craft", "recipe_id": "beacon"},
                       expected_state_digest=start["state_digest"])
    with pytest.raises(CombatSessionError, match="legal"):
        apply_decision(start, {"kind": "wait", "reward": 999},
                       expected_state_digest=start["state_digest"])


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(checksum="0" * 64),
    lambda x: x.update(after_state_digest="0" * 64),
    lambda x: x["after_bundle"]["session"]["state"].update(items={"reed": 99}),
    lambda x: x["before"]["state"].update(location="camp"),
    lambda x: x["action"].update(decision="decline"),
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x.update(extra=True),
])
def test_forged_receipts_and_rewards_rejected(mutate):
    start = new_quest(original_quest())
    record = apply_decision(
        start, {"kind": "talk", "npc_id": "guide", "decision": "aid"},
        expected_state_digest=start["state_digest"],
    )
    changed = copy.deepcopy(record)
    mutate(changed)
    with pytest.raises(CombatSessionError):
        verify_decision(changed)


def test_cli_dispatch_preview_apply_verify(capsys):
    from skeleton.__main__ import main
    assert main(["quest-decisions", "preview", "--demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["candidates"]
    start = new_quest(original_quest())
    assert cli(["apply", "--session-json", json.dumps(start),
                "--action-json", json.dumps({"kind": "wait"}),
                "--expected-state-digest", start["state_digest"]]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert cli(["apply", "--session-json", json.dumps(start),
                "--action-json", json.dumps({"kind": "wait"}),
                "--expected-state-digest", "0" * 64]) == 2
    assert "stale" in capsys.readouterr().err
