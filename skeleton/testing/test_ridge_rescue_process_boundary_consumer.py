"""Real process-boundary acceptance for the original Cinder Ridge consumer.

This exercises the published module entry point in fresh Python interpreters,
not just the in-process SlotStore API. No device certification is implied.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


MODULE = "skeleton.game.gameplay.ridge_rescue.consumer_cli"


def _run(home: Path, *args: str, stdin: str = "", timeout: int = 90) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(home)
    # Avoid inheriting an unrelated application data location on Windows.
    env["LOCALAPPDATA"] = str(home)
    return subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        timeout=timeout,
        check=False,
    )


def _json_result(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, (result.stdout, result.stderr)
    return json.loads(result.stdout)


def test_first_launch_quit_and_cold_restart_preserve_authoritative_save(tmp_path):
    home = tmp_path / "consumer-data"
    first = _run(home, "play", "--slot", "journey", "--ascii", stdin="q\n")
    assert first.returncode == 0, first.stderr
    assert "Actions:" in first.stdout
    initial = _json_result(_run(home, "status", "--slot", "journey"))
    assert initial["revision"] == 0
    assert initial["status"] == "playing"
    second = _run(home, "play", "--slot", "journey", "--ascii", stdin="0\nq\n")
    assert second.returncode == 0, second.stderr
    progressed = _json_result(_run(home, "status", "--slot", "journey"))
    assert progressed["revision"] == 1
    assert progressed["head"] != initial["head"]
    third = _run(home, "play", "--slot", "journey", "--ascii", stdin="q\n")
    assert third.returncode == 0, third.stderr
    reopened = _json_result(_run(home, "status", "--slot", "journey"))
    assert reopened["head"] == progressed["head"]
    assert reopened["revision"] == progressed["revision"]
    audit = _json_result(_run(home, "audit", "--slot", "journey"))
    assert audit["audit_entries"] == 1
    assert audit["head"] == progressed["head"]


def test_process_boundary_earned_ending_and_export_acceptance(tmp_path):
    home = tmp_path / "consumer-data"
    result = _json_result(_run(home, "acceptance", timeout=180))
    assert result["status"] == "verified-in-process"
    assert result["chapters"] == 2
    assert result["interactive_quit_restart_verified"] is True
    assert result["interactive_export_backup_verified"] is True
    assert result["backup_restore_replay_verified"] is True
    assert result["portable_export_verified"] is True
    assert result["release_certified"] is False
    assert result["windows_device_certified"] is False
    assert result["exact_head_ci_certified"] is False


@pytest.mark.parametrize("payload", ["q\n", "0\nq\n"])
def test_cold_process_rejects_corrupt_save_without_recreating_it(tmp_path, payload):
    home = tmp_path / "consumer-data"
    _json_result(_run(home, "new", "--slot", "journey"))
    database = home / "cinder-ridge" / "rescue" / "slots.sqlite3"
    if os.name == "nt":
        database = home / "CinderRidge" / "Rescue" / "slots.sqlite3"
    assert database.is_file()
    database.write_bytes(b"not a sqlite database")
    attempted = _run(home, "play", "--slot", "journey", "--ascii", stdin=payload)
    assert attempted.returncode != 0
    assert database.read_bytes() == b"not a sqlite database"
    assert "Traceback" not in attempted.stderr
