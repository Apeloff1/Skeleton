"""Interactive campaign accessibility: player turns and enemy turns."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_interactive import (
    advance_interactive, demo_interactive, new_interactive,
)
from skeleton.game.gameplay.combat_campaign_play_narration import (
    narrate_interactive, verify_interactive_narration,
)
from skeleton.game.gameplay.tactical_policy import choose_action
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_full_play_has_accessible_player_and_opponent_turns():
    session = demo_interactive()
    report = narrate_interactive(session)
    assert report["manifest"]["phase"] == "won"
    assert report["manifest"]["currency"] == 30
    assert report["manifest"]["player_turns"] == len(session["state"]["choices"])
    assert report["manifest"]["opponent_turns"] > 0
    assert report["manifest"]["caption_count"] == len(report["captions"])
    assert len(report["chapters"]) == 2
    assert all(chapter["completed"] for chapter in report["chapters"])
    assert any(row["speaker"] == "player" for row in report["captions"])
    assert any(row["speaker"] == "opponent" for row in report["captions"])
    assert verify_interactive_narration(json.loads(json.dumps(report))) == report


def test_partial_combat_checkpoint_is_narrated_without_unearned_reward():
    session = new_interactive(original_campaign())
    report = narrate_interactive(session)
    assert report["manifest"]["currency"] == 0
    assert report["manifest"]["completed_encounters"] == 0
    assert report["chapters"][0]["completed"] is False
    policy = choose_action(session["state"]["current_combat"])
    choice = {k: v for k, v in policy.items() if k != "actor_id"}
    advanced = advance_interactive(session, choice)
    later = narrate_interactive(advanced)
    assert later["manifest"]["player_turns"] >= 1
    assert later["manifest"]["caption_count"] >= report["manifest"]["caption_count"]


def test_tampered_caption_or_nested_campaign_save_rejected():
    report = narrate_interactive(demo_interactive())
    forged = copy.deepcopy(report)
    forged["captions"][0]["caption"] = "Player wins without combat"
    with pytest.raises(CombatSessionError):
        verify_interactive_narration(forged)
    forged = copy.deepcopy(report)
    forged["session"]["state"]["currency"] = 99999
    with pytest.raises(CombatSessionError):
        verify_interactive_narration(forged)


def _run(capsys, *args):
    status = main(list(args))
    output = capsys.readouterr()
    return status, json.loads(output.out or output.err)


def test_main_cli_play_narrate_and_verify(capsys):
    status, session = _run(capsys, "combat-campaign-play", "demo")
    assert status == 0
    status, report = _run(capsys, "combat-campaign-play", "narrate",
                          "--session-json", json.dumps(session))
    assert status == 0 and report["manifest"]["phase"] == "won"
    status, verified = _run(capsys, "combat-campaign-play", "narration-verify",
                            "--report-json", json.dumps(report))
    assert status == 0 and verified == report


def test_cli_invalid_narration_fails_closed(capsys):
    status, error = _run(capsys, "combat-campaign-play", "narration-verify",
                         "--report-json", '{"bad":true}')
    assert status == 2 and error["ok"] is False
