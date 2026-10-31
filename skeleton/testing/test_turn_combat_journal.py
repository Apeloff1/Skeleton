"""Source-bound offline turn combat: real canonical gameplay and CLI contracts."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_TURNS, SCHEMA, cli, new_session, normalize_scenario,
    original_demo, resume_session, simulate, verify_session,
)


def test_original_encounter_reaches_victory_and_replays() -> None:
    scenario, actions = original_demo()
    session = simulate(scenario, actions)
    assert session["state"]["phase"] == "won"
    assert session["state"]["winner"] == "wayfarers"
    assert session["state"]["tick"] == 3
    assert session["state"]["actors"]["warden"]["hp"] == 0
    assert session["save"]["state_digest"] == session["state_digest"]
    assert verify_session(json.loads(json.dumps(session))) == session


def test_authoring_order_does_not_change_source_or_turn_order() -> None:
    scenario, actions = original_demo()
    other = copy.deepcopy(scenario)
    other["actors"].reverse()
    assert simulate(other, actions) == simulate(scenario, actions)


def test_partial_save_resume_matches_one_pass_and_has_parent_lineage() -> None:
    scenario, actions = original_demo()
    initial = new_session(scenario)
    partial = resume_session(initial, actions[:2])
    restored = json.loads(json.dumps(partial))
    resumed = resume_session(restored, actions[2:])
    assert resumed == simulate(scenario, actions)
    assert resumed["save"]["parent_save_digest"] is not None


def test_guard_reduces_damage_and_rest_heals_without_exceeding_max() -> None:
    scenario, _ = original_demo()
    sequence = [
        {"kind": "guard", "actor_id": "scout"},
        {"kind": "attack", "actor_id": "warden", "target_id": "scout"},
        {"kind": "rest", "actor_id": "scout"},
    ]
    result = simulate(scenario, sequence)
    assert result["state"]["actors"]["scout"]["hp"] == 12
    assert result["state"]["actors"]["scout"]["guard"] is False


@pytest.mark.parametrize("action", [
    {"kind": "attack", "actor_id": "warden", "target_id": "scout"},
    {"kind": "attack", "actor_id": "scout", "target_id": "scout"},
    {"kind": "attack", "actor_id": "scout", "target_id": "missing"},
    {"kind": "attack", "actor_id": "scout", "target_id": "warden", "damage": 999},
    {"kind": "cast", "actor_id": "scout"},
    {"kind": "guard", "actor_id": "scout", "target_id": "warden"},
])
def test_rejects_invalid_or_unauthorized_action(action: dict) -> None:
    scenario, _ = original_demo()
    with pytest.raises(CombatSessionError):
        simulate(scenario, [action])


@pytest.mark.parametrize("change", [
    lambda s: s.update(turn_limit=MAX_TURNS + 1),
    lambda s: s.update(turn_limit=True),
    lambda s: s["actors"][0].update(attack=1.5),
    lambda s: s["actors"][0].update(id="../unsafe"),
    lambda s: s["actors"][1].update(id="scout"),
    lambda s: s["actors"][1].update(team="wayfarers"),
    lambda s: s.update(schema_version="future"),
    lambda s: s.update(extra="ignored"),
])
def test_fails_closed_on_bad_source(change) -> None:
    scenario, _ = original_demo()
    change(scenario)
    with pytest.raises(CombatSessionError):
        normalize_scenario(scenario)


@pytest.mark.parametrize("tamper", [
    lambda s: s["state"]["actors"]["scout"].update(hp=999),
    lambda s: s["journal"][0]["action"].update(target_id="scout"),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["journal"].reverse(),
    lambda s: s["save"].update(parent_save_digest=None),
    lambda s: s.update(source_digest="0" * 64),
    lambda s: s.update(event_bus_digest="0" * 64),
])
def test_replay_rejects_modified_state_or_history(tamper) -> None:
    scenario, actions = original_demo()
    session = simulate(scenario, actions)
    tamper(session)
    with pytest.raises(CombatSessionError):
        verify_session(session)


def test_turn_budget_yields_draw_without_extra_command() -> None:
    scenario, _ = original_demo()
    scenario["turn_limit"] = 1
    session = simulate(scenario, [{"kind": "guard", "actor_id": "scout"}])
    assert session["state"]["phase"] == "draw"
    with pytest.raises(CombatSessionError):
        resume_session(session, [{"kind": "rest", "actor_id": "warden"}])


def test_batch_rejection_does_not_mutate_existing_save() -> None:
    scenario, actions = original_demo()
    partial = simulate(scenario, actions[:1])
    original = copy.deepcopy(partial)
    with pytest.raises(CombatSessionError):
        resume_session(partial, [{"kind": "attack", "actor_id": "scout", "target_id": "warden"}])
    assert partial == original


def test_cli_demo_and_roundtrip(capsys) -> None:
    assert cli(["demo"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"]["phase"] == "won"
    assert cli(["verify", "--session-json", json.dumps(payload)]) == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_cli_invalid_json_is_explicit_failure(capsys) -> None:
    assert cli(["simulate", "--scenario-json", "{", "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False

def test_interactive_offline_play_with_recoverable_invalid_action() -> None:
    from io import StringIO
    from skeleton.game.gameplay.turn_combat import play_interactive
    scenario, actions = original_demo()
    invalid = {"kind": "attack", "actor_id": "warden", "target_id": "scout"}
    reader = StringIO("\n".join(json.dumps(item) for item in [invalid, *actions]) + "\n")
    writer = StringIO()
    result = play_interactive(scenario, input_stream=reader, output_stream=writer)
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert [event["event"] for event in events] == [
        "turn", "rejected", "turn", "turn", "terminal"
    ]
    assert events[1]["remaining_retries"] == 2
    assert events[-1]["session"] == result
    assert verify_session(result)["state"]["winner"] == "wayfarers"


def test_interactive_rejects_eof_and_bounded_invalid_attempts() -> None:
    from io import StringIO
    from skeleton.game.gameplay.turn_combat import play_interactive
    scenario, _ = original_demo()
    with pytest.raises(CombatSessionError, match="input ended"):
        play_interactive(scenario, input_stream=StringIO(""), output_stream=StringIO())
    with pytest.raises(CombatSessionError, match="three invalid"):
        play_interactive(
            scenario,
            input_stream=StringIO('{"kind":"bad"}\n' * 3),
            output_stream=StringIO(),
        )
