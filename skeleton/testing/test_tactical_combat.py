"""Canonical end-to-end offline tactical gameplay regression tests."""
from __future__ import annotations
import copy
import json
from io import StringIO
import pytest
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _parse_json, new_session, original_demo,
    play_interactive, resume_session, verify_session,
)
from skeleton.game.gameplay.tactical_policy import (
    POLICY_VERSION, choose_action, policy_receipt, run_autoplay,
)


def test_policy_action_and_source_bound_receipt() -> None:
    scenario, actions = original_demo()
    start = new_session(scenario)
    chosen = choose_action(start)
    assert chosen == actions[0]
    receipt = policy_receipt(start, chosen)
    assert receipt["policy"] == POLICY_VERSION
    assert len(receipt["receipt"]) == 64
    with pytest.raises(CombatSessionError, match="policy"):
        policy_receipt(start, {"kind": "rest", "actor_id": "scout"})
    assert start == new_session(scenario)


def test_autoplay_replays_deterministically() -> None:
    scenario, _ = original_demo()
    first = run_autoplay(scenario)
    assert first == run_autoplay(copy.deepcopy(scenario))
    assert first["state"]["phase"] in {"won", "draw"}
    assert 1 <= len(first["journal"]) <= scenario["turn_limit"]
    assert verify_session(json.loads(json.dumps(first))) == first


def test_tactics_reject_tampered_and_terminal_saves() -> None:
    scenario, actions = original_demo()
    finished = resume_session(new_session(scenario), actions)
    with pytest.raises(CombatSessionError, match="terminal"):
        choose_action(finished)
    bad = new_session(scenario)
    bad["state"]["actors"]["warden"]["hp"] = 0
    with pytest.raises(CombatSessionError, match="mismatch"):
        choose_action(bad)


def test_human_and_automated_opponent_play_to_completion() -> None:
    scenario, _ = original_demo()
    player = [
        {"kind": "attack", "actor_id": "scout", "target_id": "warden"},
        {"kind": "attack", "actor_id": "scout", "target_id": "warden"},
    ]
    output = StringIO()
    session = play_interactive(
        scenario, auto_teams=["reedbound"],
        input_stream=StringIO("\n".join(json.dumps(x) for x in player) + "\n"),
        output_stream=output,
    )
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert messages[-1]["event"] == "terminal"
    assert messages[-1]["session"] == session
    assert any(msg["event"] == "auto_action" for msg in messages)
    assert len([msg for msg in messages if msg["event"] == "turn"]) == 2
    assert verify_session(session) == session


def test_resumed_interactive_game_preserves_journal() -> None:
    scenario, actions = original_demo()
    saved = resume_session(new_session(scenario), actions[:1])
    result = play_interactive(
        scenario, resume=saved, auto_teams=["reedbound"],
        input_stream=StringIO(json.dumps(actions[-1]) + "\n"),
        output_stream=StringIO(),
    )
    assert result["state"]["phase"] == "won"
    assert result["journal"][0] == saved["journal"][0]
    assert verify_session(result) == result


@pytest.mark.parametrize("teams", [
    ["unknown"], ["reedbound", "reedbound"], ["wayfarers", "reedbound"],
    [True], "reedbound",
])
def test_invalid_auto_teams_fail_before_input(teams) -> None:
    scenario, _ = original_demo()
    with pytest.raises(CombatSessionError, match="auto"):
        play_interactive(
            scenario, auto_teams=teams,
            input_stream=StringIO(""), output_stream=StringIO(),
        )


def test_resumed_save_must_match_source() -> None:
    scenario, _ = original_demo()
    changed = copy.deepcopy(scenario)
    changed["encounter_id"] = "different"
    with pytest.raises(CombatSessionError, match="source"):
        play_interactive(
            changed, resume=new_session(scenario),
            input_stream=StringIO(""), output_stream=StringIO(),
        )


@pytest.mark.parametrize("raw", [
    '{"kind":"guard","kind":"attack","actor_id":"scout"}',
    '{"kind":"rest","actor_id":"scout","nested":{"x":1,"x":2}}',
    '{"kind":"rest","actor_id":"scout","weight":NaN}',
    '{"kind":"rest","actor_id":"scout","weight":Infinity}',
])
def test_duplicate_keys_and_nonfinite_json_fail_closed(raw) -> None:
    with pytest.raises(CombatSessionError, match="invalid action JSON"):
        _parse_json(raw, "action")


def test_auto_opponent_does_not_fabricate_win_on_eof() -> None:
    scenario, _ = original_demo()
    with pytest.raises(CombatSessionError, match="input ended"):
        play_interactive(
            scenario, auto_teams=["reedbound"],
            input_stream=StringIO(""), output_stream=StringIO(),
        )
