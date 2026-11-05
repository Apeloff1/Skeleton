"""Canonical offline visual comparison of two real replayed game histories."""
from __future__ import annotations

import json

import pytest

from scripts.game.game_project import _demo, main
from skeleton.ai.runtime.game_play_session import (
    GamePlaySessionError, render_play_comparison_frame, start_play_session,
)


def _capsule():
    return _demo(17, ["windows-11"], "NO", width=8, height=6)


def _control(*, left=False, right=False):
    return {"left": left, "right": right, "jump": False}


def _histories(capsule):
    return (
        start_play_session(capsule, [_control(), _control(right=True)]),
        start_play_session(capsule, [_control(), _control(left=True)]),
    )


def test_shared_spawn_and_alternate_positions_render_without_fabrication():
    capsule = _capsule()
    left, right = _histories(capsule)
    spawn = render_play_comparison_frame(capsule, left, right, 0)
    assert sum(row.count("X") for row in spawn["grid"]) == 1
    assert sum(row.count("1") + row.count("2") for row in spawn["grid"]) == 0
    assert spawn["first_divergent_frame"] == 2
    assert spawn["source_bound_replay_verified"]
    at_one = render_play_comparison_frame(capsule, left, right, 1)
    assert at_one["left_avatar"] == at_one["right_avatar"]
    at_two = render_play_comparison_frame(capsule, left, right, 2)
    assert at_two["frame"] == 2
    assert at_two["render_backend"] == "ascii_offline"
    assert at_two["native_renderer_used"] is False
    assert sum(row.count("X") + row.count("1") for row in at_two["grid"]) == 1
    assert sum(row.count("X") + row.count("2") for row in at_two["grid"]) == 1


@pytest.mark.parametrize("frame", [True, False, -1, 3, 1.0, "1", None])
def test_comparison_frame_requires_shared_integer_history(frame):
    capsule = _capsule()
    left, right = _histories(capsule)
    with pytest.raises(GamePlaySessionError):
        render_play_comparison_frame(capsule, left, right, frame)


def test_overlay_does_not_extend_shorter_history():
    capsule = _capsule()
    left = start_play_session(capsule, [_control()])
    right = start_play_session(capsule, [_control(), _control()])
    with pytest.raises(GamePlaySessionError):
        render_play_comparison_frame(capsule, left, right, 2)


def test_forged_history_never_reaches_renderer():
    capsule = _capsule()
    left, right = _histories(capsule)
    right["final_avatar"]["x"] = 100
    with pytest.raises(GamePlaySessionError):
        render_play_comparison_frame(capsule, left, right, 1)


def test_canonical_app_comparison_frame_cli(tmp_path, capsys):
    from skeleton.app.cli import run_app_cli
    capsule = _capsule()
    left, right = _histories(capsule)
    source = tmp_path / "capsule.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    first.write_text(json.dumps(left), encoding="utf-8")
    second.write_text(json.dumps(right), encoding="utf-8")
    assert run_app_cli([
        "game-project", "--render-play-comparison", str(first),
        "--other-session", str(second), "--session-capsule", str(source),
        "--at-frame", "1",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["frame"] == 1
    assert report["source_bound_replay_verified"]
    assert any("X" in row for row in report["grid"])
    assert main([
        "--render-play-comparison", str(first), "--other-session", str(second),
        "--session-capsule", str(source),
    ]) == 2
    assert main([
        "--compare-play-sessions", str(first), "--other-session", str(second),
        "--session-capsule", str(source), "--at-frame", "1",
    ]) == 2
    capsys.readouterr()
