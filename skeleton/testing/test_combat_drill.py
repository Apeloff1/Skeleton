"""End-to-end original combat lesson authoring, play, replay and CLI contracts."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.game.gameplay.combat_drill import (
    advance_drill, cli, new_drill, normalize_drill, original_drill,
    play_drill, preview_drill, simulate_drill, verify_drill,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _strike():
    return {"kind": "attack", "actor_id": "scout", "target_id": "warden"}


def test_original_lesson_plays_to_victory_with_verified_enemy_turns() -> None:
    session = simulate_drill(original_drill(), [_strike(), _strike()])
    assert session["outcome"] == "passed"
    assert session["combat"]["state"]["winner"] == "wayfarers"
    assert len(session["player_actions"]) == 2
    assert len(session["combat"]["journal"]) >= 3
    assert verify_drill(copy.deepcopy(session)) == session


def test_checkpoint_resume_is_byte_identical_to_uninterrupted_play() -> None:
    first = advance_drill(new_drill(original_drill()), _strike())
    saved = json.loads(json.dumps(first))
    assert advance_drill(saved, _strike()) == simulate_drill(
        original_drill(), [_strike(), _strike()],
    )


def test_policy_turns_are_not_user_editable_and_replayed() -> None:
    snapshot = simulate_drill(original_drill(), [_strike()])
    modified = copy.deepcopy(snapshot)
    modified["combat"]["journal"][1]["action"]["kind"] = "rest"
    with pytest.raises(CombatSessionError):
        verify_drill(modified)
    modified = copy.deepcopy(snapshot)
    modified["combat"]["state"]["actors"]["warden"]["hp"] = 999
    with pytest.raises(CombatSessionError):
        verify_drill(modified)


def test_receipt_grade_and_source_tampering_fail_closed() -> None:
    snapshot = simulate_drill(original_drill(), [_strike(), _strike()])
    for field, value in [
        ("receipt", "0" * 64),
        ("outcome", "failed"),
        ("source_digest", "0" * 64),
        ("policy_version", "untrusted-policy"),
    ]:
        modified = copy.deepcopy(snapshot)
        modified[field] = value
        with pytest.raises(CombatSessionError):
            verify_drill(modified)


def test_authored_schema_rejects_unknown_fields_and_impossible_goals() -> None:
    source = original_drill()
    source["unexpected"] = "injected"
    with pytest.raises(CombatSessionError):
        normalize_drill(source)
    source = original_drill()
    source["minimum_survivor_hp"] = 10000
    with pytest.raises(CombatSessionError, match="impossible"):
        normalize_drill(source)
    source = original_drill()
    source["max_player_actions"] = True
    with pytest.raises(CombatSessionError):
        normalize_drill(source)


def test_out_of_turn_and_friendly_fire_leave_prior_checkpoint_unchanged() -> None:
    snapshot = new_drill(original_drill())
    old = copy.deepcopy(snapshot)
    with pytest.raises(CombatSessionError):
        advance_drill(snapshot, {"kind": "rest", "actor_id": "warden"})
    with pytest.raises(CombatSessionError):
        advance_drill(snapshot, {
            "kind": "attack", "actor_id": "scout", "target_id": "scout",
        })
    assert snapshot == old


def test_action_limit_fails_even_when_combat_is_still_active() -> None:
    source = original_drill()
    source["max_player_actions"] = 1
    snapshot = advance_drill(new_drill(source), {"kind": "guard", "actor_id": "scout"})
    assert snapshot["outcome"] == "failed"
    assert verify_drill(snapshot) == snapshot
    with pytest.raises(CombatSessionError, match="terminal"):
        advance_drill(snapshot, _strike())


def test_player_defeat_and_low_health_are_not_awarded_victory() -> None:
    source = original_drill()
    source["minimum_survivor_hp"] = 12
    snapshot = simulate_drill(source, [_strike(), _strike()])
    assert snapshot["outcome"] == "failed"
    assert verify_drill(snapshot) == snapshot


def test_preview_reports_real_initial_actor_and_target() -> None:
    preview = preview_drill(original_drill())
    assert preview["first_player_actor"] == "scout"
    assert preview["legal_targets"] == ["warden"]
    assert preview["player_action_budget"] == 4


def test_interactive_player_can_complete_original_drill() -> None:
    inp = io.StringIO(json.dumps(_strike()) + "\n" + json.dumps(_strike()) + "\n")
    out = io.StringIO()
    result = play_drill(original_drill(), reader=inp, writer=out)
    assert result["outcome"] == "passed"
    events = [json.loads(line)["event"] for line in out.getvalue().splitlines()]
    assert events[0] == "drill_turn"
    assert events[-1] == "drill_terminal"
    assert events.count("drill_turn") == 2


def test_interactive_rejects_eof_without_fabricating_save() -> None:
    with pytest.raises(CombatSessionError, match="ended"):
        play_drill(original_drill(), reader=io.StringIO(""), writer=io.StringIO())


def test_cli_demo_verify_and_installed_dispatch(capsys) -> None:
    from skeleton.__main__ import main
    assert main(["combat-drill", "demo"]) == 0
    session = json.loads(capsys.readouterr().out)
    assert session["outcome"] == "passed"
    assert cli(["verify", "--session-json", json.dumps(session)]) == 0
    assert json.loads(capsys.readouterr().out) == session
    assert cli(["preview"]) == 0
    assert json.loads(capsys.readouterr().out)["legal_targets"] == ["warden"]


def test_cli_rejects_duplicate_json_keys_and_nonfinite_values(capsys) -> None:
    assert cli(["simulate", "--source-json", '{"x":1,"x":2}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert cli(["simulate", "--source-json", "NaN",
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
