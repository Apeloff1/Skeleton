"""Offline alternate-timeline comparison: real source replay and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from scripts.game.game_project import _demo, main
from skeleton.ai.runtime.game_play_session import (
    GamePlaySessionError, compare_play_sessions, fork_play_session,
    start_play_session, verify_play_session,
)


def _capsule():
    return _demo(17, ["windows-11"], "NO", width=8, height=6)


def _control(*, left=False, right=False):
    return {"left": left, "right": right, "jump": False}


def test_identical_and_divergent_histories_are_verified():
    capsule = _capsule()
    left = start_play_session(capsule, [_control(), _control(right=True)])
    same = compare_play_sessions(capsule, left, copy.deepcopy(left))
    assert same["identical_history"] is True
    assert same["shared_prefix_frames"] == 2
    assert same["first_divergent_frame"] is None
    alternate = fork_play_session(capsule, left, 1, [_control(left=True)])
    diff = compare_play_sessions(capsule, left, alternate)
    assert diff["identical_history"] is False
    assert diff["shared_prefix_frames"] == 1
    assert diff["first_divergent_frame"] == 2
    assert diff["left_session_sha256"] != diff["right_session_sha256"]
    assert diff["source_bound_replay_verified"] is True
    assert diff["native_renderer_used"] is False
    assert verify_play_session(capsule, alternate)["source_bound_replay_verified"]


def test_shorter_history_diverges_at_next_frame():
    capsule = _capsule()
    first = start_play_session(capsule, [_control()])
    second = start_play_session(capsule, [_control(), _control()])
    report = compare_play_sessions(capsule, first, second)
    assert report["shared_prefix_frames"] == 1
    assert report["first_divergent_frame"] == 2
    assert report["left_frame_count"] == 1
    assert report["right_frame_count"] == 2


@pytest.mark.parametrize("field,value", [
    ("frame_count", 99), ("victory_frame", 1),
    ("trace_sha256", "0" * 64), ("native_export_created", True),
    ("offline_replay", 1),
])
def test_forged_history_never_authorizes_comparison(field, value):
    capsule = _capsule()
    first = start_play_session(capsule, [_control()])
    second = copy.deepcopy(first)
    second[field] = value
    with pytest.raises(GamePlaySessionError):
        compare_play_sessions(capsule, first, second)


def test_changed_capsule_rejects_both_histories():
    capsule = _capsule()
    first = start_play_session(capsule, [_control()])
    second = start_play_session(capsule, [_control(right=True)])
    capsule["tilemap"][1] = "########"
    with pytest.raises(ValueError):
        compare_play_sessions(capsule, first, second)


def test_comparison_is_read_only_and_deterministic():
    capsule = _capsule()
    first = start_play_session(capsule, [_control()])
    second = start_play_session(capsule, [_control(right=True)])
    before = json.dumps([capsule, first, second], sort_keys=True)
    assert compare_play_sessions(capsule, first, second) == compare_play_sessions(capsule, first, second)
    assert json.dumps([capsule, first, second], sort_keys=True) == before


def test_canonical_app_comparison_cli(tmp_path, capsys):
    from skeleton.app.cli import run_app_cli
    capsule = _capsule()
    source = tmp_path / "capsule.json"
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    left.write_text(json.dumps(start_play_session(capsule, [_control()])), encoding="utf-8")
    right.write_text(json.dumps(start_play_session(capsule, [_control(right=True)])), encoding="utf-8")
    assert run_app_cli([
        "game-project", "--compare-play-sessions", str(left),
        "--other-session", str(right), "--session-capsule", str(source),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["first_divergent_frame"] == 1
    assert report["shared_prefix_frames"] == 0
    assert report["source_bound_replay_verified"]


def test_comparison_cli_fails_closed_on_invalid_flags_and_symlink(tmp_path, capsys):
    capsule = _capsule()
    source = tmp_path / "capsule.json"
    saved = tmp_path / "saved.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    saved.write_text(json.dumps(start_play_session(capsule, [_control()])), encoding="utf-8")
    assert main(["--compare-play-sessions", str(saved), "--session-capsule", str(source)]) == 2
    assert main(["--catalog", "--other-session", str(saved)]) == 2
    assert main([
        "--compare-play-sessions", str(saved), "--other-session", str(saved),
        "--session-capsule", str(source), "--save-session", str(tmp_path / "new.json"),
    ]) == 2
    assert not (tmp_path / "new.json").exists()
    link = tmp_path / "linked.json"
    link.symlink_to(saved)
    assert main([
        "--compare-play-sessions", str(saved), "--other-session", str(link),
        "--session-capsule", str(source),
    ]) == 1
    assert "rejected" in capsys.readouterr().err
