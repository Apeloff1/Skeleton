"""Real canonical offline keyboard gameplay and save/replay tests."""
from __future__ import annotations

from io import StringIO
import json
import sys

import pytest

from scripts.game.game_project import _demo, main
from skeleton.ai.runtime.game_play_session import (
    GamePlaySessionError, start_play_session, verify_play_session,
)
from skeleton.ai.runtime.game_play_terminal import (
    MAX_COMMAND_BYTES, parse_terminal_control, run_terminal_play,
)


def _capsule():
    return _demo(17, ["windows-11"], "NO", width=8, height=6)


def test_terminal_parser_admits_real_controller_combinations():
    assert parse_terminal_control("dw\n") == {
        "left": False, "right": True, "jump": True,
    }
    assert parse_terminal_control("Aw") == {
        "left": True, "right": False, "jump": True,
    }
    assert parse_terminal_control(".") == {
        "left": False, "right": False, "jump": False,
    }
    assert parse_terminal_control("q") is None


@pytest.mark.parametrize("bad", ["ad", "aa", "ww", "left", "d.", "a\x00", "🙂", "a" * 17])
def test_terminal_parser_rejects_ambiguous_or_oversized_commands(bad):
    with pytest.raises(GamePlaySessionError):
        parse_terminal_control(bad)


def test_terminal_play_uses_real_canonical_simulation_and_durable_receipt():
    capsule = _capsule()
    output = StringIO()
    result = run_terminal_play(capsule, None, StringIO("d\n.\nq\n"), output)
    assert result["frames_played"] == 2
    assert result["total_frames"] == 2
    assert result["terminal_backend"] == "ascii_turn_based"
    assert result["native_renderer_used"] is False
    assert output.getvalue().count("Controls:") == 3
    assert "Frame 2" in output.getvalue()
    saved = result["session"]
    assert saved == start_play_session(capsule, [
        {"left": False, "right": True, "jump": False},
        {"left": False, "right": False, "jump": False},
    ])
    assert verify_play_session(capsule, saved)["source_bound_replay_verified"]


def test_terminal_resume_replays_parent_and_preserves_parent_state():
    capsule = _capsule()
    first = run_terminal_play(capsule, None, StringIO(".\nq\n"), StringIO())
    saved = first["session"]
    original = json.dumps(saved, sort_keys=True)
    second = run_terminal_play(capsule, saved, StringIO("d\nq\n"), StringIO())
    assert second["total_frames"] == saved["frame_count"] + 1
    assert json.dumps(saved, sort_keys=True) == original
    assert verify_play_session(capsule, second["session"])["source_bound_replay_verified"]


@pytest.mark.parametrize("text", ["", "q\n", "ad\n", "x" * (MAX_COMMAND_BYTES + 2)])
def test_terminal_no_input_or_bad_input_fails_without_forging_a_save(text):
    with pytest.raises(GamePlaySessionError):
        run_terminal_play(_capsule(), None, StringIO(text), StringIO())


@pytest.mark.parametrize("limit", [0, 65, True, 1.0, "1"])
def test_terminal_frame_budget_is_strictly_typed(limit):
    with pytest.raises(GamePlaySessionError):
        run_terminal_play(_capsule(), None, StringIO("d\n"), StringIO(), max_frames=limit)


def test_terminal_budget_does_not_consume_unbounded_input():
    commands = StringIO("d\n" * 70)
    result = run_terminal_play(_capsule(), None, commands, StringIO(), max_frames=1)
    assert result["frames_played"] == 1
    assert commands.read().startswith("d\n")


def test_terminal_rejects_tampered_parent_before_consuming_controls():
    capsule = _capsule()
    saved = start_play_session(capsule, [{"left": False, "right": False, "jump": False}])
    saved["trace_sha256"] = "0" * 64
    stream = StringIO("d\n")
    with pytest.raises(GamePlaySessionError):
        run_terminal_play(capsule, saved, stream, StringIO())
    assert stream.read() == "d\n"


def test_canonical_cli_terminal_play_and_resume(tmp_path, capsys, monkeypatch):
    from skeleton.app.cli import run_app_cli

    capsule = _capsule()
    source = tmp_path / "capsule.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", StringIO("d\n.\nq\n"))
    assert run_app_cli([
        "game-project", "--terminal-play-capsule", str(source),
        "--save-session", str(first),
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["frames_played"] == 2
    assert receipt["native_renderer_used"] is False
    assert verify_play_session(capsule, json.loads(first.read_text()))[
        "source_bound_replay_verified"
    ]
    monkeypatch.setattr(sys, "stdin", StringIO("w\nq\n"))
    assert run_app_cli([
        "game-project", "--terminal-resume-session", str(first),
        "--session-capsule", str(source), "--save-session", str(second),
        "--terminal-max-frames", "1",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["total_frames"] == 3
    assert second.exists()


def test_terminal_cli_fails_closed_on_invalid_flags_and_existing_output(tmp_path, capsys, monkeypatch):
    source = tmp_path / "capsule.json"
    saved = tmp_path / "save.json"
    source.write_text(json.dumps(_capsule()), encoding="utf-8")
    saved.write_text("preserve me", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", StringIO("d\nq\n"))
    assert main([
        "--terminal-play-capsule", str(source), "--save-session", str(saved),
    ]) == 1
    assert saved.read_text() == "preserve me"
    assert main(["--catalog", "--terminal-max-frames", "1"]) == 2
    assert main([
        "--terminal-play-capsule", str(source), "--save-session", str(tmp_path / "new.json"),
        "--controls-file", str(source),
    ]) == 2
    assert main([
        "--terminal-play-capsule", str(source), "--save-session", str(tmp_path / "new.json"),
        "--terminal-max-frames", "0",
    ]) == 2


def test_terminal_gracefully_saves_last_admissible_frame():
    from skeleton.ai.runtime.game_play_session import resume_play_session

    capsule = _capsule()
    idle = {"left": False, "right": False, "jump": False}
    prior = start_play_session(capsule, [idle] * 64)
    for _ in range(14):
        prior = resume_play_session(capsule, prior, [idle] * 64)
    prior = resume_play_session(capsule, prior, [idle] * 63)
    assert prior["frame_count"] == 1023
    stream = StringIO(".\n" * 5)
    result = run_terminal_play(capsule, prior, stream, StringIO(), max_frames=5)
    assert result["total_frames"] == 1024
    assert result["frames_played"] == 1
    assert verify_play_session(capsule, result["session"])["source_bound_replay_verified"]
    assert stream.read().startswith(".\n")
    with pytest.raises(GamePlaySessionError):
        run_terminal_play(capsule, result["session"], StringIO(".\n"), StringIO())
