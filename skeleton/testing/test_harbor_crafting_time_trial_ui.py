"""Interactive time-trial terminal acceptance without bypassing game rules."""
from __future__ import annotations

from io import StringIO
from pathlib import Path
import subprocess
import sys

from skeleton.game.gameplay.harbor_crafting import (
    canonical, decode, demo_actions, load_source,
)
from skeleton.game.gameplay.harbor_crafting_ui import (
    play_live, scripted_demo_commands,
)
from skeleton.game.gameplay.harbor_crafting_time_trials import (
    verify_time_trial_report,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def fixtures():
    world = load_source(ROOT / "harbor_lantern_quay.json")
    course = decode((ROOT / "harbor_lantern_quay_time_trial.json").read_bytes())
    return world, course


def _report(transcript):
    row = next(line for line in transcript.splitlines() if line.startswith("TRIAL_REPORT "))
    return decode(row[len("TRIAL_REPORT "):].encode())


def test_player_wins_live_trial_with_earned_gold_and_portable_replay():
    world, course = fixtures()
    output = StringIO()
    commands = StringIO("hint\n" + scripted_demo_commands())
    status = play_live(world, commands, output, course=course)
    transcript = output.getvalue()
    assert status == 0
    assert "TRIAL_PROGRESS 0/4 checkpoints" in transcript
    assert "TRIAL finished gold" in transcript
    assert "VICTORY beacon" in transcript
    assert verify_time_trial_report(_report(transcript), require_finish=True)["medal"] == "gold"


def test_story_victory_with_wrong_trial_choice_returns_failure_and_save():
    world, course = fixtures()
    commands = scripted_demo_commands().replace("signal\n", "shelter\n")
    output = StringIO()
    status = play_live(world, StringIO(commands), output, course=course)
    assert status == 2
    assert "VICTORY safe_harbor" in output.getvalue()
    assert "TRIAL incomplete no-medal" in output.getvalue()
    assert "CHECKPOINT " in output.getvalue()
    assert verify_time_trial_report(_report(output.getvalue()))["medal"] is None


def test_interactive_undo_redo_recalculates_checkpoint_progress():
    world, course = fixtures()
    output = StringIO()
    status = play_live(
        world, StringIO("east\nhint\nundo\nhint\nredo\nhint\nquit\n"),
        output, course=course,
    )
    assert status == 2
    text = output.getvalue()
    assert "TRIAL_PROGRESS 1/4 checkpoints" in text
    assert "TRIAL_PROGRESS 0/4 checkpoints" in text
    assert text.count("TRIAL_PROGRESS 1/4 checkpoints") == 2
    assert "QUIT: no victory" in text


def test_invalid_command_never_advances_checkpoint_or_gameplay():
    world, course = fixtures()
    output = StringIO()
    status = play_live(
        world, StringIO("north\nhint\nquit\n"), output, course=course,
    )
    assert status == 2
    assert "REJECTED movement collision" in output.getvalue()
    assert "TRIAL_PROGRESS 0/4 checkpoints" in output.getvalue()
    assert "VICTORY " not in output.getvalue()


def test_cli_trial_live_is_reachable_and_exports_verified_trial_report():
    trial = ROOT / "harbor_lantern_quay_time_trial.json"
    result = subprocess.run(
        CLI + ["trial-live", "--trial", str(trial)],
        input=scripted_demo_commands().encode(),
        capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    report = _report(result.stdout.decode())
    assert verify_time_trial_report(report, require_finish=True)["finish_tick"] == 18
    assert canonical(report) in result.stdout


def test_cli_trial_live_missing_course_fails_without_fake_success():
    result = subprocess.run(
        CLI + ["trial-live"],
        input=scripted_demo_commands().encode(),
        capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"--trial is required" in result.stderr
