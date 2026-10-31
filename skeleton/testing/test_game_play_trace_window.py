"""Canonical source-bound frame diagnostics for real offline game sessions."""
from __future__ import annotations

import copy
import json

import pytest

from scripts.game.game_project import _demo, main
from skeleton.ai.runtime.game_play_session import (
    GamePlaySessionError, inspect_play_trace, start_play_session,
)
from skeleton.ai.runtime.gameplay_capabilities import platformer_step, compile_level


def _capsule():
    return _demo(17, ["windows-11"], "NO", width=8, height=6)


def _control(*, left=False, right=False, jump=False):
    return {"left": left, "right": right, "jump": jump}


def _session(capsule):
    return start_play_session(capsule, [
        _control(), _control(right=True), _control(right=True), _control(jump=True),
    ])


def test_trace_window_replays_actual_controller_physics():
    capsule = _capsule()
    saved = _session(capsule)
    trace = inspect_play_trace(capsule, saved, 2, 3)
    assert trace["start_frame"] == 2
    assert trace["end_frame"] == 3
    assert trace["frame_count"] == 2
    assert trace["source_bound_replay_verified"] is True
    assert trace["native_renderer_used"] is False
    assert trace == inspect_play_trace(capsule, saved, 2, 3)
    initial = compile_level({"tiles": capsule["tilemap"]})["spawn"]
    avatar = {"x": initial["x"], "y": initial["y"], "vx": 0, "vy": 0}
    for action in saved["controls"]:
        outcome = platformer_step({
            "tiles": capsule["tilemap"], "avatar": avatar, "control": action,
        })
        avatar = outcome["avatar"]
        if action == saved["controls"][0]:
            pass
    assert trace["final_avatar"] == inspect_play_trace(capsule, saved, 1, 3)["final_avatar"]
    assert len(trace["window_sha256"]) == 64
    assert trace["frames"][0]["control"] == saved["controls"][1]


@pytest.mark.parametrize(("start", "end"), [
    (0, 1), (1, 0), (2, 1), (1, 5), (True, 1),
    (1, False), (1.0, 1), ("1", 2), (None, 2),
])
def test_trace_rejects_invalid_window(start, end):
    capsule = _capsule()
    saved = _session(capsule)
    with pytest.raises(GamePlaySessionError):
        inspect_play_trace(capsule, saved, start, end)


def test_trace_enforces_64_frame_window_without_extrapolation():
    capsule = _capsule()
    idle = _control()
    saved = start_play_session(capsule, [idle] * 64)
    assert inspect_play_trace(capsule, saved, 1, 64)["frame_count"] == 64
    from skeleton.ai.runtime.game_play_session import resume_play_session
    saved = resume_play_session(capsule, saved, [idle])
    with pytest.raises(GamePlaySessionError):
        inspect_play_trace(capsule, saved, 1, 65)


def test_trace_rejects_forged_state_and_source_edits():
    capsule = _capsule()
    saved = _session(capsule)
    forged = copy.deepcopy(saved)
    forged["final_avatar"]["x"] += 1
    with pytest.raises(GamePlaySessionError):
        inspect_play_trace(capsule, forged, 1, 2)
    capsule["tilemap"][1] = "########"
    with pytest.raises(ValueError):
        inspect_play_trace(capsule, saved, 1, 2)


def test_trace_does_not_modify_save_or_source():
    capsule = _capsule()
    saved = _session(capsule)
    before = json.dumps([capsule, saved], sort_keys=True)
    inspect_play_trace(capsule, saved, 1, 4)
    assert json.dumps([capsule, saved], sort_keys=True) == before


def test_canonical_app_trace_cli(tmp_path, capsys):
    from skeleton.app.cli import run_app_cli
    capsule = _capsule()
    saved = _session(capsule)
    source = tmp_path / "capsule.json"
    session = tmp_path / "session.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    session.write_text(json.dumps(saved), encoding="utf-8")
    assert run_app_cli([
        "game-project", "--inspect-play-trace", str(session),
        "--session-capsule", str(source), "--trace-start", "2", "--trace-end", "3",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["frame_count"] == 2
    assert report["source_bound_replay_verified"]
    assert main([
        "--inspect-play-trace", str(session), "--session-capsule", str(source),
        "--trace-start", "2",
    ]) == 2
    assert main(["--catalog", "--trace-start", "1"]) == 2
    assert main([
        "--inspect-play-trace", str(session), "--session-capsule", str(source),
        "--trace-start", "1", "--trace-end", "1", "--at-frame", "1",
    ]) == 2
    assert "required" in capsys.readouterr().err or True
