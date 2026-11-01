"""Weather-gated scene play: collision, wait, source, save/replay and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    cli, new_session, normalize_weather, original_weather_demo,
    resume_session, simulate, verify_session,
)


def test_original_weather_travel_reaches_real_canonical_victory():
    source, actions = original_weather_demo()
    result = simulate(source, actions)
    assert result["state"]["phase"] == "won"
    assert result["state"]["scene"]["state"]["scene_id"] == "sanctuary"
    assert result["state"]["scene"]["state"]["inventory"] == ["brass_key"]
    assert result["state"]["tick"] == 3
    assert verify_session(json.loads(json.dumps(result))) == result


def test_weather_collision_blocks_exit_without_mutating_checkpoint():
    source, actions = original_weather_demo()
    first = new_session(source)
    original = copy.deepcopy(first)
    with pytest.raises(SceneTravelError, match="blocked"):
        resume_session(first, [actions[1]])
    assert first == original
    waited = resume_session(first, [{"kind": "wait"}])
    assert waited["state"]["weather"] == "clear"
    with pytest.raises(SceneTravelError, match="uncollected"):
        resume_session(waited, [actions[1]])


def test_wait_then_collect_then_travel_and_replay_checkpoint():
    source, actions = original_weather_demo()
    first = resume_session(new_session(source), [{"kind": "wait"}, actions[0]])
    second = resume_session(json.loads(json.dumps(first)), actions[1:])
    assert second["state"]["phase"] == "won"
    assert second == simulate(source, [{"kind": "wait"}, *actions])


def test_wait_is_bounded_and_cannot_fabricate_victory():
    source, _ = original_weather_demo()
    source["world"]["step_limit"] = 2
    session = simulate(source, [{"kind": "wait"}, {"kind": "wait"}])
    assert session["state"]["phase"] == "draw"
    assert session["state"]["scene"]["state"]["phase"] == "active"
    with pytest.raises(SceneTravelError, match="terminal"):
        resume_session(session, [{"kind": "wait"}])


@pytest.mark.parametrize("change", [
    lambda x: x.update(cycle=[]),
    lambda x: x.update(cycle=["sunshine"]),
    lambda x: x.update(cycle=["clear", True]),
    lambda x: x["blocked_exits"][0].update(exit_id="missing"),
    lambda x: x["blocked_exits"][0].update(conditions=["fog"]),
    lambda x: x["blocked_exits"][0].update(conditions=["storm", "storm"]),
    lambda x: x["blocked_exits"].append(copy.deepcopy(x["blocked_exits"][0])),
    lambda x: x.update(extra="untrusted"),
])
def test_bad_weather_sources_rejected(change):
    source, _ = original_weather_demo()
    change(source)
    with pytest.raises(SceneTravelError):
        normalize_weather(source)


@pytest.mark.parametrize("change", [
    lambda x: x["state"].update(phase="won"),
    lambda x: x["state"]["scene"]["state"].update(scene_id="sanctuary"),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x["journal"].reverse(),
    lambda x: x["save"].update(parent_save_digest=None),
    lambda x: x.update(source_digest="0" * 64),
])
def test_tampered_weather_saves_rejected(change):
    source, actions = original_weather_demo()
    saved = simulate(source, actions)
    change(saved)
    with pytest.raises(SceneTravelError):
        verify_session(saved)


def test_cli_demo_verify_and_json_duplicate_key_rejection(capsys):
    assert cli(["demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--session-json", json.dumps(saved)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"a":1,"a":2}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_cli_rejects_nonfinite_json_constants(capsys):
    assert cli(["simulate", "--source-json", '{"a":NaN}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
