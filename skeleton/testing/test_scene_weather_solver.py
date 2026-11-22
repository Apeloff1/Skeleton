"""Weather route solver: legal movement, replay, bounded uncertainty, CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    new_session, original_weather_demo, resume_session, simulate, verify_session,
)
from skeleton.game.gameplay.scene_weather_solver import plan_weather


def test_shortest_route_replays_through_canonical_weather_and_inventory():
    source, actions = original_weather_demo()
    route = plan_weather(source)
    assert route["status"] == "solved"
    assert route["complete"] is True
    assert route["actions"] == actions
    assert route["terminal_session"] == simulate(source, actions)
    assert verify_session(route["terminal_session"]) == route["terminal_session"]
    assert route["terminal_state_digest"] == route["terminal_session"]["state_digest"]


def test_resume_from_verified_checkpoint_has_shorter_legal_route():
    source, actions = original_weather_demo()
    checkpoint = resume_session(new_session(source), [actions[0]])
    route = plan_weather(session=json.loads(json.dumps(checkpoint)))
    assert route["status"] == "solved"
    assert route["actions"] == actions[1:]
    assert route["terminal_session"] == simulate(source, actions)
    assert route["start_state_digest"] == checkpoint["state_digest"]


def test_terminal_victory_is_zero_action_route_and_terminal_loss_is_unreachable():
    source, actions = original_weather_demo()
    victory = simulate(source, actions)
    result = plan_weather(session=victory)
    assert result["status"] == "solved"
    assert result["actions"] == []
    assert result["terminal_session"] == victory
    source["world"]["step_limit"] = 1
    drawn = simulate(source, [{"kind": "wait"}])
    assert drawn["state"]["phase"] == "draw"
    result = plan_weather(session=drawn)
    assert result["status"] == "unreachable" and result["complete"]


def test_budget_exhaustion_is_inconclusive_not_false_unreachable():
    source, _ = original_weather_demo()
    for kwargs in ({"max_depth": 0}, {"max_states": 1}):
        result = plan_weather(source, **kwargs)
        assert result["status"] == "inconclusive"
        assert result["complete"] is False
        assert result["terminal_session"] is None


def test_permanently_blocked_exit_exhausts_small_world_without_victory():
    source, _ = original_weather_demo()
    source["cycle"] = ["storm"]
    source["blocked_exits"][0]["conditions"] = ["storm"]
    source["world"]["step_limit"] = 3
    result = plan_weather(source, max_depth=8)
    assert result["status"] == "unreachable"
    assert result["complete"] is True


@pytest.mark.parametrize("limits", [
    {"max_states": True}, {"max_states": 0}, {"max_states": 513},
    {"max_depth": -1}, {"max_depth": 65}, {"max_depth": 1.5},
])
def test_bad_limits_fail_closed(limits):
    source, _ = original_weather_demo()
    with pytest.raises(SceneTravelError):
        plan_weather(source, **limits)


def test_corrupted_resume_is_rejected_before_search():
    source, actions = original_weather_demo()
    checkpoint = simulate(source, actions[:1])
    bad = copy.deepcopy(checkpoint)
    bad["state"]["weather"] = "clear"
    with pytest.raises(SceneTravelError):
        plan_weather(session=bad)


def test_installed_cli_solve_and_verified_replay(capsys):
    assert main(["scene-weather", "solve", "--demo"]) == 0
    route = json.loads(capsys.readouterr().out)
    assert route["status"] == "solved"
    assert main([
        "scene-weather", "verify", "--session-json",
        json.dumps(route["terminal_session"]),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == route["terminal_session"]


def test_cli_source_checkpoint_and_invalid_input(capsys):
    source, actions = original_weather_demo()
    assert main([
        "scene-weather", "solve", "--source-json", json.dumps(source),
        "--max-states", "256", "--max-depth", "8",
    ]) == 0
    route = json.loads(capsys.readouterr().out)
    assert route["actions"] == actions
    checkpoint = simulate(source, actions[:1])
    assert main([
        "scene-weather", "solve", "--session-json", json.dumps(checkpoint),
    ]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["actions"] == actions[1:]
    assert main([
        "scene-weather", "solve", "--source-json", '{"x":1,"x":2}',
    ]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
