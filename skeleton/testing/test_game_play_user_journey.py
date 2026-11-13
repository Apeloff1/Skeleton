"""Actual offline user journey: author -> play -> save -> seek -> fork -> transfer.

These are canonical application CLI entrypoints, not stand-in mock engines.
No third-party assets, network access, native binaries or rights clearance.
"""
from __future__ import annotations

from io import StringIO
import json
import socket
import sys

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.ai.runtime.game_play_bundle import verify_play_bundle
from skeleton.ai.runtime.game_play_session import verify_play_session


def _invoke(capsys, args):
    assert run_app_cli(["game-project", *args]) == 0
    return json.loads(capsys.readouterr().out)


def test_full_offline_original_game_user_journey(tmp_path, capsys, monkeypatch):
    # Prevent accidental network calls from being silently treated as offline.
    def forbidden_network(*_args, **_kwargs):
        raise AssertionError("gameplay acceptance must not contact the network")

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    capsule = tmp_path / "original.json"
    first = tmp_path / "first-save.json"
    forked = tmp_path / "forked-save.json"
    transferred = tmp_path / "transfer.json"
    alternative = tmp_path / "transfer-alternative.json"
    actions = tmp_path / "alternate-actions.json"
    actions.write_text(json.dumps({
        "controls": [{"left": True, "right": False, "jump": False}],
    }), encoding="utf-8")

    author = _invoke(capsys, [
        "--demo-project", str(capsule), "--targets", "windows-11",
        "--width", "8", "--height", "6", "--seed", "17",
    ])
    assert author["no_native_console_binary_created"]
    assert capsule.exists()
    project = json.loads(capsule.read_text())
    assert project["project_id"] == "original-demo-17"

    monkeypatch.setattr(sys, "stdin", StringIO("d\n.\nq\n"))
    played = _invoke(capsys, [
        "--terminal-play-capsule", str(capsule), "--save-session", str(first),
    ])
    assert played["frames_played"] == 2
    assert played["terminal_backend"] == "ascii_turn_based"
    assert played["native_renderer_used"] is False
    save = json.loads(first.read_text())
    assert verify_play_session(project, save)["source_bound_replay_verified"]

    inspected = _invoke(capsys, [
        "--inspect-play-frame", str(first), "--session-capsule", str(capsule),
        "--at-frame", "0",
    ])
    assert inspected["frame"] == 0
    assert inspected["source_session_sha256"] == save["session_sha256"]
    assert inspected["grid"][1][1] == "@"

    fork = _invoke(capsys, [
        "--fork-play-session", str(first), "--session-capsule", str(capsule),
        "--at-frame", "0", "--controls-file", str(actions),
        "--save-session", str(forked),
    ])
    assert fork["fork_frame"] == 0
    assert fork["forked_from_session_sha256"] == save["session_sha256"]
    alternative_save = json.loads(forked.read_text())
    assert alternative_save["frame_count"] == 1
    assert verify_play_session(project, alternative_save)["source_bound_replay_verified"]
    assert json.loads(first.read_text()) == save

    exported = _invoke(capsys, [
        "--export-play-bundle", str(forked), "--session-capsule", str(capsule),
        "--bundle-output", str(transferred),
    ])
    assert exported["offline_replay_verified"]
    checked = _invoke(capsys, ["--verify-play-bundle", str(transferred)])
    assert checked["bundle_sha256"] == exported["bundle_sha256"]
    portable = json.loads(transferred.read_text())
    assert verify_play_bundle(portable)["offline_replay_verified"]

    branched = _invoke(capsys, [
        "--fork-play-bundle", str(transferred), "--at-frame", "0",
        "--controls-file", str(actions), "--bundle-output", str(alternative),
    ])
    assert branched["offline_replay_verified"]
    assert branched["forked_from_bundle_sha256"] == portable["bundle_sha256"]
    assert verify_play_bundle(json.loads(alternative.read_text()))[
        "offline_replay_verified"
    ]
    assert json.loads(transferred.read_text()) == portable


def test_source_edit_invalidates_prior_save_and_transfer(tmp_path, capsys):
    source = tmp_path / "capsule.json"
    saved = tmp_path / "save.json"
    bundle = tmp_path / "bundle.json"
    actions = tmp_path / "actions.json"
    actions.write_text(json.dumps({
        "controls": [{"left": False, "right": False, "jump": False}],
    }), encoding="utf-8")
    _invoke(capsys, [
        "--demo-project", str(source), "--targets", "windows-11",
        "--width", "8", "--height", "6", "--seed", "17",
    ])
    _invoke(capsys, [
        "--play-capsule", str(source), "--controls-file", str(actions),
        "--save-session", str(saved),
    ])
    _invoke(capsys, [
        "--export-play-bundle", str(saved), "--session-capsule", str(source),
        "--bundle-output", str(bundle),
    ])
    edited = json.loads(source.read_text())
    edited["tilemap"][1] = edited["tilemap"][1].replace("S", ".")
    source.write_text(json.dumps(edited), encoding="utf-8")
    assert run_app_cli([
        "game-project", "--verify-play-session", str(saved),
        "--session-capsule", str(source),
    ]) == 1
    assert "rejected" in capsys.readouterr().err
    assert _invoke(capsys, ["--verify-play-bundle", str(bundle)])[
        "offline_replay_verified"
    ]


def test_offline_journey_rejects_existing_output_and_linked_input(tmp_path, capsys):
    source = tmp_path / "source.json"
    _invoke(capsys, [
        "--demo-project", str(source), "--targets", "windows-11",
        "--width", "8", "--height", "6", "--seed", "17",
    ])
    link = tmp_path / "source-link.json"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not supported on target platform")
    output = tmp_path / "save.json"
    output.write_text("original bytes", encoding="utf-8")
    actions = tmp_path / "actions.json"
    actions.write_text(json.dumps({
        "controls": [{"left": False, "right": False, "jump": False}],
    }), encoding="utf-8")
    assert run_app_cli([
        "game-project", "--play-capsule", str(link),
        "--controls-file", str(actions), "--save-session", str(output),
    ]) == 1
    assert output.read_text() == "original bytes"
    assert "rejected" in capsys.readouterr().err
