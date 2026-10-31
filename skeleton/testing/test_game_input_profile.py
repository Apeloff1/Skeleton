"""Accessible offline terminal input: canonical app and source-bound replay."""
from __future__ import annotations

from io import StringIO
import json
import sys

import pytest

from scripts.game.game_project import _demo, main
from skeleton.ai.runtime.game_input_profile import (
    SCHEMA, terminal_profile_receipt, validate_terminal_input_profile,
)
from skeleton.ai.runtime.game_play_session import (
    GamePlaySessionError, start_play_session, verify_play_session,
)
from skeleton.ai.runtime.game_play_terminal import parse_terminal_control, run_terminal_play


def _capsule():
    return _demo(17, ["windows-11"], "NO", width=8, height=6)


def _profile(**changes):
    bindings = {"left": "j", "right": "l", "jump": "i", "wait": ".", "quit": "x"}
    bindings.update(changes)
    return {"schema_version": SCHEMA, "bindings": bindings}


def test_remap_executes_real_simulation_and_source_bound_replay():
    capsule = _capsule()
    profile = _profile()
    output = StringIO()
    result = run_terminal_play(capsule, None, StringIO("Li\n.\nx\n"), output, input_profile=profile)
    assert result["frames_played"] == 2
    assert "l=right" in output.getvalue()
    assert "x=quit" in output.getvalue()
    assert result["input_profile_sha256"] == terminal_profile_receipt(profile)["profile_sha256"]
    expected = start_play_session(capsule, [
        {"left": False, "right": True, "jump": True},
        {"left": False, "right": False, "jump": False},
    ])
    assert result["session"] == expected
    assert verify_play_session(capsule, result["session"])["source_bound_replay_verified"]
    assert parse_terminal_control("Li", input_profile=profile) == expected["controls"][0]
    assert parse_terminal_control("x", input_profile=profile) is None
    with pytest.raises(GamePlaySessionError):
        parse_terminal_control("d", input_profile=profile)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version="v2"),
    lambda p: p.update(admin=True),
    lambda p: p["bindings"].update(left="l"),
    lambda p: p["bindings"].update(wait="z"),
    lambda p: p["bindings"].update(quit="."),
    lambda p: p["bindings"].update(right="."),
    lambda p: p["bindings"].update(jump="🙂"),
    lambda p: p["bindings"].update(left="J"),
    lambda p: p["bindings"].update(right="long"),
    lambda p: p["bindings"].update(left=True),
    lambda p: p["bindings"].pop("jump"),
])
def test_invalid_profile_rejected_before_input(mutation):
    profile = _profile()
    mutation(profile)
    stream = StringIO("l\n")
    with pytest.raises(GamePlaySessionError):
        run_terminal_play(_capsule(), None, stream, StringIO(), input_profile=profile)
    assert stream.read() == "l\n"


@pytest.mark.parametrize("command", ["jl", "ll", "q", "l.", "ll" * 9, "\x00"])
def test_invalid_remapped_commands_fail_closed(command):
    with pytest.raises(GamePlaySessionError):
        parse_terminal_control(command, input_profile=_profile())


def test_profile_does_not_mutate_source_or_save_and_resume_changes_layout():
    capsule = _capsule()
    profile = _profile()
    original = json.dumps(profile, sort_keys=True)
    first = run_terminal_play(capsule, None, StringIO("l\nx\n"), StringIO(), input_profile=profile)
    second = run_terminal_play(capsule, first["session"], StringIO("d\nq\n"), StringIO())
    assert second["session"] == start_play_session(capsule, [
        {"left": False, "right": True, "jump": False},
        {"left": False, "right": True, "jump": False},
    ])
    assert json.dumps(profile, sort_keys=True) == original
    assert "input_profile_sha256" not in second["session"]


def test_canonical_app_accepts_keymap_and_exclusive_save(tmp_path, capsys, monkeypatch):
    from skeleton.app.cli import run_app_cli
    capsule = _capsule()
    source = tmp_path / "capsule.json"
    keymap = tmp_path / "keymap.json"
    output = tmp_path / "save.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    keymap.write_text(json.dumps(_profile()), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", StringIO("l\nx\n"))
    assert run_app_cli([
        "game-project", "--terminal-play-capsule", str(source),
        "--terminal-input-profile", str(keymap), "--save-session", str(output),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["input_profile_sha256"] == terminal_profile_receipt(_profile())["profile_sha256"]
    assert verify_play_session(capsule, json.loads(output.read_text()))["source_bound_replay_verified"]
    assert run_app_cli([
        "game-project", "--terminal-play-capsule", str(source),
        "--terminal-input-profile", str(keymap), "--save-session", str(output),
    ]) == 1
    assert json.loads(output.read_text())["frame_count"] == 1
    capsys.readouterr()


def test_cli_rejects_bad_keymap_and_symlink_before_play(tmp_path, capsys, monkeypatch):
    source = tmp_path / "capsule.json"
    source.write_text(json.dumps(_capsule()), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_profile(left="l")), encoding="utf-8")
    output = tmp_path / "saved.json"
    monkeypatch.setattr(sys, "stdin", StringIO("l\n"))
    assert main(["--catalog", "--terminal-input-profile", str(bad)]) == 2
    assert main([
        "--terminal-play-capsule", str(source), "--terminal-input-profile", str(bad),
        "--save-session", str(output),
    ]) == 1
    assert not output.exists()
    link = tmp_path / "link.json"
    link.symlink_to(bad)
    assert main([
        "--terminal-play-capsule", str(source), "--terminal-input-profile", str(link),
        "--save-session", str(output),
    ]) == 1
    assert not output.exists()
    assert "rejected" in capsys.readouterr().err


def test_profile_receipt_is_stable_but_not_authority():
    assert validate_terminal_input_profile() == {
        "left": "a", "right": "d", "jump": "w", "wait": ".", "quit": "q",
    }
    assert terminal_profile_receipt(_profile()) == terminal_profile_receipt(_profile())
    assert terminal_profile_receipt(_profile()) != terminal_profile_receipt()
