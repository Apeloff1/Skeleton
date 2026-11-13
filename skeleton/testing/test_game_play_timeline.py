"""Canonical offline replay seek/fork and portable alternate-timeline acceptance."""
from __future__ import annotations

import json

import pytest

from scripts.game.game_project import _demo, main
from skeleton.ai.runtime.game_play_bundle import (
    fork_play_bundle, pack_play_bundle, verify_play_bundle,
)
from skeleton.ai.runtime.game_play_session import (
    GamePlaySessionError, fork_play_session, inspect_play_frame,
    render_play_frame, start_play_session, verify_play_session,
)


def _capsule():
    return _demo(17, ["windows-11"], "NO", width=8, height=6)


def _control(*, left=False, right=False, jump=False):
    return {"left": left, "right": right, "jump": jump}


def _save():
    return start_play_session(
        _capsule(), [_control(), _control(right=True), _control()],
    )


def test_frame_zero_and_prefix_replay_are_source_bound_and_read_only():
    capsule = _capsule()
    session = _save()
    original = json.dumps(session, sort_keys=True)
    initial = inspect_play_frame(capsule, session, 0)
    assert initial["frame"] == 0
    assert initial["avatar"]["x"] == 1
    assert initial["avatar"]["y"] == 1
    assert initial["source_session_sha256"] == session["session_sha256"]
    for frame in range(session["frame_count"] + 1):
        observed = inspect_play_frame(capsule, session, frame)
        expected = (
            start_play_session(capsule, session["controls"][:frame])
            if frame else None
        )
        if expected is not None:
            assert observed["avatar"] == expected["final_avatar"]
            assert observed["prefix_trace_sha256"] == expected["trace_sha256"]
        rendered = render_play_frame(capsule, session, frame)
        assert rendered["render_backend"] == "ascii_offline"
        assert sum(row.count("@") for row in rendered["grid"]) == 1
    assert json.dumps(session, sort_keys=True) == original


def test_fork_at_spawn_and_midway_produces_replayable_independent_save():
    capsule = _capsule()
    session = _save()
    original = json.dumps(session, sort_keys=True)
    alternate = [_control(left=True)]
    from_spawn = fork_play_session(capsule, session, 0, alternate)
    assert from_spawn == start_play_session(capsule, alternate)
    middle = fork_play_session(capsule, session, 1, alternate)
    assert middle == start_play_session(capsule, session["controls"][:1] + alternate)
    assert middle["frame_count"] == 2
    assert verify_play_session(capsule, middle)["source_bound_replay_verified"]
    assert json.dumps(session, sort_keys=True) == original


@pytest.mark.parametrize("frame", [True, False, -1, 4, 1.0, "1", None])
def test_seek_and_fork_reject_non_integer_or_out_of_range_frames(frame):
    capsule = _capsule()
    session = _save()
    with pytest.raises(GamePlaySessionError):
        inspect_play_frame(capsule, session, frame)
    with pytest.raises(GamePlaySessionError):
        fork_play_session(capsule, session, frame, [_control()])


def test_fork_rejects_invalid_batch_and_history_limit():
    capsule = _capsule()
    session = _save()
    with pytest.raises(GamePlaySessionError):
        fork_play_session(capsule, session, 1, [])
    with pytest.raises(GamePlaySessionError):
        fork_play_session(capsule, session, 1, [_control()] * 65)
    with pytest.raises(GamePlaySessionError):
        fork_play_session(capsule, session, 1, [{"left": 0, "right": False, "jump": False}])
    with pytest.raises(GamePlaySessionError):
        fork_play_session(capsule, session, 1, [{"left": False, "right": False}])
    full = start_play_session(capsule, [_control()] * 64)
    for _ in range(15):
        from skeleton.ai.runtime.game_play_session import resume_play_session
        full = resume_play_session(capsule, full, [_control()] * 64)
    assert full["frame_count"] == 1024
    with pytest.raises(GamePlaySessionError):
        fork_play_session(capsule, full, 1024, [_control()])


def test_forged_parent_save_never_authorizes_seek_or_fork():
    capsule = _capsule()
    session = _save()
    session["final_avatar"]["x"] += 1
    with pytest.raises(GamePlaySessionError):
        inspect_play_frame(capsule, session, 1)
    with pytest.raises(GamePlaySessionError):
        fork_play_session(capsule, session, 1, [_control()])


def test_portable_bundle_fork_and_tamper_rejection():
    capsule = _capsule()
    original = pack_play_bundle(capsule, _save())
    alternative = fork_play_bundle(original, 1, [_control(left=True)])
    assert verify_play_bundle(alternative)["offline_replay_verified"]
    assert alternative["capsule"] == original["capsule"]
    assert alternative["session"]["frame_count"] == 2
    assert original["session"]["frame_count"] == 3
    assert alternative == fork_play_bundle(original, 1, [_control(left=True)])
    original["session"]["trace_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        fork_play_bundle(original, 1, [_control()])


def test_canonical_app_seek_and_fork_cli(tmp_path, capsys):
    from skeleton.app.cli import run_app_cli

    capsule = _capsule()
    session = _save()
    source = tmp_path / "source.json"
    saved = tmp_path / "saved.json"
    controls = tmp_path / "controls.json"
    output = tmp_path / "fork.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    saved.write_text(json.dumps(session), encoding="utf-8")
    controls.write_text(json.dumps({"controls": [_control(left=True)]}), encoding="utf-8")
    assert run_app_cli([
        "game-project", "--inspect-play-frame", str(saved),
        "--session-capsule", str(source), "--at-frame", "0",
    ]) == 0
    seek = json.loads(capsys.readouterr().out)
    assert seek["frame"] == 0
    assert sum(row.count("@") for row in seek["grid"]) == 1
    assert run_app_cli([
        "game-project", "--fork-play-session", str(saved),
        "--session-capsule", str(source), "--at-frame", "1",
        "--controls-file", str(controls), "--save-session", str(output),
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["fork_frame"] == 1
    assert receipt["forked_from_session_sha256"] == session["session_sha256"]
    assert verify_play_session(capsule, json.loads(output.read_text()))[
        "source_bound_replay_verified"
    ]
    assert run_app_cli([
        "game-project", "--fork-play-session", str(saved),
        "--session-capsule", str(source), "--at-frame", "1",
        "--controls-file", str(controls), "--save-session", str(output),
    ]) == 1
    assert "rejected" in capsys.readouterr().err


def test_portable_fork_cli_and_invalid_argument_combinations(tmp_path, capsys):
    capsule = _capsule()
    original = pack_play_bundle(capsule, _save())
    bundle = tmp_path / "bundle.json"
    actions = tmp_path / "controls.json"
    output = tmp_path / "alternative.json"
    bundle.write_text(json.dumps(original), encoding="utf-8")
    actions.write_text(json.dumps({"controls": [_control()]}), encoding="utf-8")
    assert main([
        "--fork-play-bundle", str(bundle), "--at-frame", "1",
        "--controls-file", str(actions), "--bundle-output", str(output),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["fork_frame"] == 1
    assert result["forked_from_bundle_sha256"] == original["bundle_sha256"]
    assert verify_play_bundle(json.loads(output.read_text()))["offline_replay_verified"]
    assert main(["--catalog", "--at-frame", "0"]) == 2
    assert main(["--fork-play-bundle", str(bundle), "--bundle-output", str(tmp_path / "bad.json"),
                 "--controls-file", str(actions)]) == 2
    assert main(["--verify-play-bundle", str(bundle), "--at-frame", "0"]) == 2
