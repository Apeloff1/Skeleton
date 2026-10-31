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

def test_canonical_app_cli_delegates_game_project_play_session(tmp_path, capsys):
    from skeleton.app.cli import run_app_cli
    source = tmp_path / "source.json"
    controls = tmp_path / "controls.json"
    saved = tmp_path / "session.json"
    source.write_text(json.dumps(_capsule()), encoding="utf-8")
    controls.write_text(json.dumps({"controls": [_move()]}), encoding="utf-8")
    assert run_app_cli([
        "game-project", "--play-capsule", str(source),
        "--controls-file", str(controls), "--save-session", str(saved),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["frame_count"] == 1
    assert run_app_cli([
        "game-project", "--verify-play-session", str(saved),
        "--session-capsule", str(source),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["source_bound_replay_verified"]

@pytest.mark.parametrize(("field", "forgery"), [
    ("frame_count", True),
    ("offline_replay", 1),
    ("native_export_created", 0),
])
def test_typed_save_replay_rejects_bool_int_confusion(field, forgery):
    capsule = _capsule()
    session = start_play_session(capsule, [_move()])
    session[field] = forgery
    with pytest.raises(GamePlaySessionError):
        verify_play_session(capsule, session)


def test_ascii_renderer_only_accepts_replayed_verified_session():
    from skeleton.ai.runtime.game_play_session import render_play_session
    capsule = _capsule()
    session = start_play_session(capsule, [_move()])
    rendered = render_play_session(capsule, session)
    assert rendered["render_backend"] == "ascii_offline"
    assert rendered["native_renderer_used"] is False
    assert sum(row.count("@") for row in rendered["grid"]) == 1
    assert rendered["session_sha256"] == session["session_sha256"]
    session["frame_count"] = 999
    with pytest.raises(GamePlaySessionError):
        render_play_session(capsule, session)


def test_canonical_app_renders_source_bound_session(tmp_path, capsys):
    from skeleton.app.cli import run_app_cli
    source = tmp_path / "source.json"
    saved = tmp_path / "session.json"
    source.write_text(json.dumps(_capsule()), encoding="utf-8")
    saved.write_text(json.dumps(start_play_session(_capsule(), [_move()])), encoding="utf-8")
    assert run_app_cli([
        "game-project", "--render-play-session", str(saved),
        "--session-capsule", str(source),
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["render_backend"] == "ascii_offline"
    assert any("@" in row for row in receipt["grid"])

def test_portable_bundle_round_trip_and_recovery(tmp_path, capsys):
    from skeleton.ai.runtime.game_play_bundle import (
        pack_play_bundle, verify_play_bundle, resume_play_bundle,
    )
    capsule = _capsule()
    saved = start_play_session(capsule, [_move()])
    bundle = pack_play_bundle(capsule, saved)
    assert verify_play_bundle(bundle)["offline_replay_verified"]
    assert bundle == pack_play_bundle(capsule, saved)
    if saved["victory_frame"] is None:
        recovered = resume_play_bundle(bundle, [_move()])
        assert verify_play_bundle(recovered)["frame_count"] == 2
    source = tmp_path / "source.json"
    session = tmp_path / "session.json"
    package = tmp_path / "portable.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    session.write_text(json.dumps(saved), encoding="utf-8")
    assert main([
        "--export-play-bundle", str(session), "--session-capsule", str(source),
        "--bundle-output", str(package),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["offline_replay_verified"]
    assert main(["--verify-play-bundle", str(package)]) == 0
    assert json.loads(capsys.readouterr().out)["offline_replay_verified"]


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(body_bytes=True),
    lambda b: b.update(bundle_sha256="0" * 64),
    lambda b: b["session"].update(frame_count=999),
    lambda b: b["capsule"].update(legal_release_authorized=True),
    lambda b: b.update(untrusted="extra"),
])
def test_portable_bundle_rejects_tampering(mutation):
    from skeleton.ai.runtime.game_play_bundle import (
        GamePlayBundleError, pack_play_bundle, verify_play_bundle,
    )
    bundle = pack_play_bundle(_capsule(), start_play_session(_capsule(), [_move()]))
    mutation(bundle)
    with pytest.raises((GamePlayBundleError, GamePlaySessionError, ValueError)):
        verify_play_bundle(bundle)
