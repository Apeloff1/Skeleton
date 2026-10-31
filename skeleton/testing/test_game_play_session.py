"""Canonical CLI and engine tests for offline source-bound play sessions."""
from __future__ import annotations

import json

import pytest

from scripts.game.game_project import _demo, main
from skeleton.ai.runtime.game_play_session import (
    GamePlaySessionError, MAX_BATCH_FRAMES, resume_play_session,
    start_play_session, verify_play_session,
)


def _capsule():
    return _demo(17, ["windows-11"], "NO", width=8, height=6)


def _move(right=False, left=False, jump=False):
    return {"left": left, "right": right, "jump": jump}


def test_replay_is_deterministic_and_does_not_mutate_source():
    capsule = _capsule()
    before = json.dumps(capsule, sort_keys=True)
    controls = [_move(), _move(right=True)]
    first = start_play_session(capsule, controls)
    assert first == start_play_session(capsule, controls)
    assert first["frame_count"] == 2
    assert first["native_export_created"] is False
    assert verify_play_session(capsule, first)["source_bound_replay_verified"]
    assert json.dumps(capsule, sort_keys=True) == before


def test_resume_verifies_prior_history_and_recomputes_result():
    capsule = _capsule()
    first = start_play_session(capsule, [_move()])
    if first["victory_frame"] is not None:
        pytest.skip("initial frame is already terminal")
    resumed = resume_play_session(capsule, first, [_move(right=True)])
    assert resumed == start_play_session(capsule, [_move(), _move(right=True)])
    assert resumed["session_sha256"] != first["session_sha256"]
    assert verify_play_session(capsule, resumed)["frame_count"] == 2


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(final_avatar={"x": 2, "y": 2, "vx": 0, "vy": 0}),
    lambda s: s.update(victory_frame=1),
    lambda s: s.update(trace_sha256="0" * 64),
    lambda s: s.update(session_sha256="0" * 64),
    lambda s: s["controls"][0].update(right=True),
    lambda s: s.update(native_export_created=True),
    lambda s: s.update(unexpected="admin"),
])
def test_restore_rejects_tampering_even_if_session_is_json(mutation):
    capsule = _capsule()
    saved = start_play_session(capsule, [_move()])
    mutation(saved)
    with pytest.raises(GamePlaySessionError):
        verify_play_session(capsule, saved)


def test_capsule_identity_is_rechecked_not_just_session_checksum():
    capsule = _capsule()
    saved = start_play_session(capsule, [_move()])
    capsule["tilemap"][1] = "########"
    with pytest.raises(ValueError):
        verify_play_session(capsule, saved)


@pytest.mark.parametrize("bad", [
    [], [_move()] * (MAX_BATCH_FRAMES + 1),
    [{"left": 1, "right": False, "jump": False}],
    [{"left": False, "right": False}],
    [{"left": False, "right": False, "jump": False, "shell": "run"}],
    "left",
])
def test_controls_are_bounded_and_fail_closed(bad):
    with pytest.raises(GamePlaySessionError):
        start_play_session(_capsule(), bad)


def test_source_bound_play_cli_start_resume_and_verify(tmp_path, capsys):
    capsule = _capsule()
    source = tmp_path / "capsule.json"
    actions = tmp_path / "actions.json"
    saved = tmp_path / "save.json"
    resumed = tmp_path / "resumed.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    actions.write_text(json.dumps({"controls": [_move()]}), encoding="utf-8")
    assert main([
        "--play-capsule", str(source),
        "--controls-file", str(actions), "--save-session", str(saved),
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["frame_count"] == 1
    assert receipt["native_export_created"] is False
    assert saved.exists()
    assert main([
        "--verify-play-session", str(saved), "--session-capsule", str(source),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["source_bound_replay_verified"]
    if json.loads(saved.read_text())["victory_frame"] is None:
        assert main([
            "--resume-play-session", str(saved), "--session-capsule", str(source),
            "--controls-file", str(actions), "--save-session", str(resumed),
        ]) == 0
        assert json.loads(capsys.readouterr().out)["frame_count"] == 2
        assert resumed.exists()
    assert main([
        "--play-capsule", str(source), "--controls-file", str(actions),
        "--save-session", str(saved),
    ]) == 1  # exclusive save never overwrites existing state
    capsys.readouterr()


def test_play_cli_rejects_unknown_or_malformed_controls(tmp_path, capsys):
    source = tmp_path / "capsule.json"
    source.write_text(json.dumps(_capsule()), encoding="utf-8")
    actions = tmp_path / "actions.json"
    actions.write_text(json.dumps({"controls": [_move()], "admin": True}))
    assert main([
        "--play-capsule", str(source), "--controls-file", str(actions),
        "--save-session", str(tmp_path / "saved.json"),
    ]) == 1
    assert not (tmp_path / "saved.json").exists()
    assert "rejected" in capsys.readouterr().err


def test_no_play_only_flags_on_other_cli_operations(capsys):
    assert main(["--catalog", "--save-session", "unexpected.json"]) == 2
    assert "play-session" in capsys.readouterr().err
