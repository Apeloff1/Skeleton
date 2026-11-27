"""The preflight must never represent a failed or partial run as success."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from scripts import deep_production_scan as scan


@pytest.mark.parametrize("returncode", [0, 1, 17, -9])
def test_check_reports_actual_exit_code(returncode):
    with patch.object(scan.subprocess, "run", return_value=subprocess.CompletedProcess([], returncode)) as run:
        assert scan.run_check(("check.py",), 5) == (returncode == 0, f"exit {returncode}")
    args, kwargs = run.call_args
    assert args[0] == [scan.sys.executable, "check.py"]
    assert kwargs["cwd"] == scan.ROOT
    assert kwargs["timeout"] == 5
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL


@pytest.mark.parametrize(
    ("error", "reason"),
    [(subprocess.TimeoutExpired(["check"], 5), "timeout"), (OSError("launch failed"), "process launch failed")],
)
def test_launch_and_timeout_fail_closed(error, reason):
    with patch.object(scan.subprocess, "run", side_effect=error):
        assert scan.run_check(("check.py",), 5) == (False, reason)


def test_main_attempts_every_check_and_rejects_partial_success(capsys):
    outcomes = [(False, "exit 1")] + [(True, "exit 0")] * (len(scan.CHECKS) - 1)
    with patch.object(scan, "run_check", side_effect=outcomes) as run:
        assert scan.main() == 1
        assert run.call_count == len(scan.CHECKS)
    assert f"{len(scan.CHECKS) - 1}/{len(scan.CHECKS)}" in capsys.readouterr().out


def test_main_accepts_only_complete_success():
    with patch.object(scan, "run_check", return_value=(True, "exit 0")):
        assert scan.main() == 0
