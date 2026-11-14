"""Portable weather checkpoints: source, replay, inventory and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    original_weather_demo, simulate, verify_session,
)
from skeleton.game.gameplay.scene_weather_package import (
    original_package_demo, package_weather, resume_package, verify_package,
)


def test_portable_weather_checkpoint_replays_to_real_victory():
    source, actions = original_weather_demo()
    checkpoint = original_package_demo()
    assert checkpoint["manifest"]["tick"] == 1
    assert checkpoint["manifest"]["weather"] == "clear"
    assert checkpoint["manifest"]["inventory"] == ["brass_key"]
    assert verify_package(json.loads(json.dumps(checkpoint))) == checkpoint
    completed = resume_package(checkpoint, actions[1:])
    assert completed["manifest"]["phase"] == "won"
    assert completed["manifest"]["scene_id"] == "sanctuary"
    assert completed["snapshot"] == simulate(source, actions)
    assert verify_session(completed["snapshot"]) == completed["snapshot"]
    assert resume_package(completed, []) == completed


def test_pack_from_independent_replay_and_reject_stale_source():
    source, actions = original_weather_demo()
    checkpoint = simulate(source, actions[:1])
    package = package_weather(source, checkpoint)
    assert verify_package(package) == package
    stale = copy.deepcopy(source)
    stale["cycle"] = ["clear", "storm"]
    with pytest.raises(SceneTravelError, match="source mismatch"):
        package_weather(stale, checkpoint)


@pytest.mark.parametrize("mutate", [
    lambda x: x["manifest"].update(inventory=["forged_key"]),
    lambda x: x["manifest"].update(weather="storm"),
    lambda x: x["snapshot"]["state"]["scene"]["state"].update(
        inventory=["forged_key"]),
    lambda x: x["snapshot"]["journal"][0].update(receipt="0" * 64),
    lambda x: x["snapshot"]["save"].update(parent_save_digest="0" * 64),
    lambda x: x.update(snapshot_digest="0" * 64),
    lambda x: x.update(receipt="0" * 64),
])
def test_tampered_portable_weather_fails_closed(mutate):
    package = original_package_demo()
    bad = copy.deepcopy(package)
    mutate(bad)
    with pytest.raises(SceneTravelError):
        verify_package(bad)


def test_invalid_action_cannot_advance_checkpoint_or_grant_inventory():
    source, actions = original_weather_demo()
    package = original_package_demo()
    original = copy.deepcopy(package)
    with pytest.raises(SceneTravelError):
        resume_package(package, [{
            "kind": "scene", "action": {"kind": "travel", "exit_id": "missing"},
        }])
    assert package == original
    with pytest.raises(SceneTravelError):
        resume_package(package, {"kind": "wait"})
    assert resume_package(package, actions[1:])["manifest"]["phase"] == "won"


def test_installed_cli_demo_verify_resume_and_export(capsys):
    source, actions = original_weather_demo()
    assert main(["scene-weather-package", "demo"]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert main([
        "scene-weather-package", "verify",
        "--package-json", json.dumps(bundle),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == bundle
    assert main([
        "scene-weather-package", "resume",
        "--package-json", json.dumps(bundle),
        "--actions-json", json.dumps(actions[1:]),
    ]) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["manifest"]["phase"] == "won"
    assert main([
        "scene-weather-package", "pack",
        "--source-json", json.dumps(source),
        "--session-json", json.dumps(completed["snapshot"]),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == completed


def test_cli_duplicate_key_rejection_and_no_release(capsys):
    assert main([
        "scene-weather-package", "verify",
        "--package-json", '{"a":1,"a":2}',
    ]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
