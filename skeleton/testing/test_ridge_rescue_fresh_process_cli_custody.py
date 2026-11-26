"""Fresh-process consumer CLI persistence and portable export acceptance.

Exercises real user commands with isolated save custody; this is host-neutral,
not evidence of Windows device qualification or final-head CI.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


MODULE = "skeleton.game.gameplay.ridge_rescue.consumer_cli"


def _run(root: Path, *args: str, payload: bytes | None = None):
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(root / "data")
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    return subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        timeout=45,
        check=False,
    )


def _ok(result):
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert b"Traceback" not in result.stderr
    return json.loads(result.stdout)


def test_fresh_process_slot_survives_restart_and_export_verifies(tmp_path):
    first = _ok(_run(tmp_path, "new", "--slot", "fresh"))
    assert first["revision"] == 0
    assert first["status"] == "playing"
    restored = _ok(_run(tmp_path, "status", "--slot", "fresh"))
    assert restored["head"] == first["head"]
    assert restored["revision"] == first["revision"]
    assert restored["actions"]

    # A rejected command must not commit a turn or replace the save head.
    invalid = _run(tmp_path, "step", "--slot", "fresh",
                   "--expected-head", first["head"],
                   "--action", '{"verb":"rest","verb":"move"}')
    assert invalid.returncode == 2
    assert b"duplicate" in invalid.stderr.lower()
    assert b"Traceback" not in invalid.stderr
    assert _ok(_run(tmp_path, "status", "--slot", "fresh"))["head"] == first["head"]

    action = json.dumps(restored["actions"][0], sort_keys=True)
    advanced = _ok(_run(tmp_path, "step", "--slot", "fresh",
                        "--expected-head", first["head"], "--action", action))
    assert advanced["revision"] == 1
    assert advanced["head"] != first["head"]
    assert _ok(_run(tmp_path, "status", "--slot", "fresh"))["head"] == advanced["head"]

    export = _ok(_run(tmp_path, "export", "--slot", "fresh"))
    artifact = Path(export["path"])
    assert artifact.is_file()
    verified = _ok(_run(tmp_path, "verify-export", "--file", "-", payload=artifact.read_bytes()))
    assert verified["verified"] is True
    assert verified["head"] == advanced["head"]
    assert _ok(_run(tmp_path, "audit", "--slot", "fresh"))["head"] == advanced["head"]


def test_fresh_process_rejects_stale_revision_without_mutation(tmp_path):
    state = _ok(_run(tmp_path, "new", "--slot", "stale"))
    action = json.dumps(state["actions"][0], sort_keys=True)
    committed = _ok(_run(tmp_path, "step", "--slot", "stale",
                         "--expected-head", state["head"], "--action", action))
    stale = _run(tmp_path, "step", "--slot", "stale",
                 "--expected-head", state["head"], "--action", action)
    assert stale.returncode == 2
    assert b"Traceback" not in stale.stderr
    actual = _ok(_run(tmp_path, "status", "--slot", "stale"))
    assert actual["head"] == committed["head"]
    assert actual["revision"] == committed["revision"]
