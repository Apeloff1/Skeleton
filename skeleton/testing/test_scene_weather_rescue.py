"""NPC rescue via weather gates, exposure, earned rewards and replay."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_rescue import (
    SCHEMA, advance_rescue, new_rescue, normalize_rescue, original_rescue,
    package_rescue, play_rescue, verify_package, verify_rescue,
)


def test_original_npc_rescue_uses_canonical_weather_and_earned_reward():
    source, actions = original_rescue()
    result = play_rescue(source, actions)
    assert result["state"]["phase"] == "won"
    assert result["state"]["earned"] == 25
    assert result["state"]["npcs"]["canal_medic"] == {
        "status": "safe", "exposure": 1,
    }
    assert result["weather_session"]["state"]["scene"]["state"]["scene_id"] == "gate"
    assert verify_rescue(json.loads(json.dumps(result))) == result
    assert len(result["state"]["journal"]) == 4


def test_checkpoint_resume_is_bit_identical_and_source_not_mutated():
    source, actions = original_rescue()
    original = copy.deepcopy(source)
    first = play_rescue(source, actions[:2])
    before = copy.deepcopy(first)
    resumed = play_rescue(source, actions[2:], resume=first)
    assert resumed == play_rescue(source, actions)
    assert first == before and source == original
    assert first["save"]["parent_digest"]
    assert resumed["save"]["parent_digest"]


def test_canonical_weather_gate_and_npc_location_rejections():
    source, actions = original_rescue()
    with pytest.raises(SceneTravelError, match="weather"):
        play_rescue(source, [actions[2]])
    with pytest.raises(SceneTravelError, match="unavailable"):
        play_rescue(source, [actions[3]])
    with pytest.raises(SceneTravelError, match="unavailable"):
        play_rescue(source, [actions[0], actions[0]])
    with pytest.raises(SceneTravelError, match="unknown"):
        play_rescue(source, [{"kind": "rescue", "npc_id": "forged"}])


def test_storm_exposure_can_fail_without_unearned_rewards():
    source, actions = original_rescue()
    source["npcs"][0]["max_storm_exposure"] = 0
    played = play_rescue(source, actions[:3])
    assert played["state"]["phase"] == "lost"
    assert played["state"]["earned"] == 0
    assert played["state"]["npcs"]["canal_medic"]["status"] == "lost"
    assert verify_rescue(played) == played


def test_deadline_expiration_and_shelter_reward_not_recoverable():
    source, actions = original_rescue()
    source["npcs"][0]["deadline"] = 2
    played = play_rescue(source, actions[:3])
    assert played["state"]["phase"] == "lost"
    assert played["state"]["earned"] == 0
    with pytest.raises(SceneTravelError, match="terminal"):
        advance_rescue(played, actions[3])


@pytest.mark.parametrize("mutate", [
    lambda x: x["npcs"][0].update(npc_id=""),
    lambda x: x["npcs"][0].update(origin_scene="unknown"),
    lambda x: x["npcs"][0].update(shelter_scene="quay"),
    lambda x: x["npcs"][0].update(shelter_scene="sanctuary"),
    lambda x: x["npcs"][0].update(deadline=13),
    lambda x: x["npcs"][0].update(max_storm_exposure=9),
    lambda x: x["npcs"][0].update(reward=0),
    lambda x: x["npcs"].append(copy.deepcopy(x["npcs"][0])),
    lambda x: x.update(extra="forged"),
])
def test_invalid_rescue_sources_fail_closed(mutate):
    source, _ = original_rescue()
    mutate(source)
    with pytest.raises(SceneTravelError):
        normalize_rescue(source)


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"].update(earned=999),
    lambda x: x["state"]["npcs"]["canal_medic"].update(status="lost"),
    lambda x: x["state"]["journal"][0].update(receipt="0" * 64),
    lambda x: x["weather_session"]["state"].update(weather="storm"),
    lambda x: x["save"].update(parent_digest=None),
    lambda x: x.update(source_digest="0" * 64),
])
def test_forged_rescue_replay_and_save_rejected(mutate):
    source, actions = original_rescue()
    valid = play_rescue(source, actions)
    bad = copy.deepcopy(valid)
    mutate(bad)
    with pytest.raises(SceneTravelError):
        verify_rescue(bad)


def test_portable_export_rejects_forged_reputation():
    source, actions = original_rescue()
    result = package_rescue(play_rescue(source, actions))
    assert result["manifest"]["earned"] == 25
    assert verify_package(result) == result
    bad = copy.deepcopy(result)
    bad["manifest"]["earned"] = 999
    with pytest.raises(SceneTravelError):
        verify_package(bad)


def test_installed_cli_end_to_end_source_to_save_to_export(capsys):
    assert main(["scene-weather-rescue", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["schema_version"] == SCHEMA
    assert saved["state"]["earned"] == 25
    assert main([
        "scene-weather-rescue", "verify",
        "--session-json", json.dumps(saved),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert main([
        "scene-weather-rescue", "pack",
        "--session-json", json.dumps(saved),
    ]) == 0
    package = json.loads(capsys.readouterr().out)
    assert main([
        "scene-weather-rescue", "unpack",
        "--package-json", json.dumps(package),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == package
