"""Exercise the shipped consumer entry point in a fresh interpreter.

In-process acceptance cannot detect import-time failures, CLI output regressions,
or accidentally leaked consumer certification flags. This is host-neutral and
does not replace Windows device qualification.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from skeleton.game.gameplay.ridge_rescue.consumer_acceptance import CONTRACT


def _invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root)
    return subprocess.run(
        [sys.executable, "-m", "skeleton.game.gameplay.ridge_rescue.consumer_cli", *arguments],
        cwd=root,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )


def test_fresh_process_can_complete_real_consumer_acceptance():
    completed = _invoke("acceptance")
    assert completed.returncode == 0, completed.stderr
    assert not completed.stderr.strip()
    lines = completed.stdout.splitlines()
    assert len(lines) == 1, completed.stdout
    report = json.loads(lines[0])
    assert report["schema"] == CONTRACT
    assert report["status"] == "verified-in-process"
    assert report["chapters"] == 2
    assert report["actions"] > 0
    assert report["saved_revision"] == report["actions"]
    assert report["terminal_commands"] == report["actions"]
    assert report["interactive_quit_restart_verified"] is True
    assert report["interactive_export_backup_verified"] is True
    assert report["backup_restore_replay_verified"] is True
    assert report["portable_export_verified"] is True
    assert report["windows_device_certified"] is False
    assert report["exact_head_ci_certified"] is False
    assert report["release_certified"] is False


def test_fresh_process_acceptance_is_deterministic():
    first = _invoke("acceptance")
    second = _invoke("acceptance")
    assert first.returncode == second.returncode == 0
    a = json.loads(first.stdout)
    b = json.loads(second.stdout)
    for field in ("schema", "status", "head", "chapters", "actions",
                  "saved_revision", "terminal_commands", "terminal_frames"):
        assert a[field] == b[field]


def test_consumer_cli_rejects_missing_action_without_traceback():
    result = _invoke("step", "--slot", "adventure")
    assert result.returncode == 2
    assert "required" in result.stderr.lower()
    assert "Traceback" not in result.stderr
