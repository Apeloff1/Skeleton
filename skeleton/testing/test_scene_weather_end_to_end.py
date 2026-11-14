"""End-to-end CLI scene weather acceptance and fail-closed save handling."""
from __future__ import annotations

import copy
import json

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_weather import original_weather_demo


def _run(capsys, *args):
    status = main(list(args))
    output = capsys.readouterr()
    return status, json.loads(output.out) if output.out else json.loads(output.err)


def test_weather_source_to_scene_runtime_to_replay_export(capsys):
    source, actions = original_weather_demo()
    status, terminal = _run(capsys, "scene-weather", "demo")
    assert status == 0
    assert terminal["state"]["phase"] == "won"
    assert terminal["state"]["scene"]["state"]["ending"] == "victory"

    status, verified = _run(
        capsys, "scene-weather", "verify",
        "--session-json", json.dumps(terminal),
    )
    assert status == 0 and verified == terminal

    status, replayed = _run(
        capsys, "scene-weather", "simulate",
        "--source-json", json.dumps(source),
        "--actions-json", json.dumps(actions),
    )
    assert status == 0 and replayed == terminal

    status, scene_save = _run(
        capsys, "scene-travel", "verify",
        "--session-json", json.dumps(terminal["state"]["scene"]),
    )
    assert status == 0 and scene_save == terminal["state"]["scene"]


def test_resume_wait_checkpoint_and_refuse_unearned_exit(capsys):
    source, actions = original_weather_demo()
    status, checkpoint = _run(
        capsys, "scene-weather", "simulate",
        "--source-json", json.dumps(source),
        "--actions-json", json.dumps([actions[0]]),
    )
    assert status == 0 and checkpoint["state"]["weather"] == "clear"

    status, resumed = _run(
        capsys, "scene-weather", "resume",
        "--session-json", json.dumps(checkpoint),
        "--actions-json", json.dumps(actions[1:]),
    )
    assert status == 0 and resumed["state"]["phase"] == "won"

    status, blocked = _run(
        capsys, "scene-weather", "simulate",
        "--source-json", json.dumps(source),
        "--actions-json", json.dumps([actions[1]]),
    )
    assert status == 2 and blocked["ok"] is False


def test_cli_rejects_modified_reward_like_inventory_and_save_lineage(capsys):
    status, valid = _run(capsys, "scene-weather", "demo")
    assert status == 0
    modified = copy.deepcopy(valid)
    modified["state"]["scene"]["state"]["inventory"].append("unearned_key")
    status, error = _run(
        capsys, "scene-weather", "verify",
        "--session-json", json.dumps(modified),
    )
    assert status == 2 and error["ok"] is False
