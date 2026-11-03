"""Source-checkout consumer process smoke: real CLI, restart, ending and export.

Run on a target Windows laptop with:
    py -3 -m skeleton.game.gameplay.ridge_rescue consumer smoke

This runs in a disposable appdata directory, never the player's real save.
It produces machine-readable evidence but is not installer or release approval.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .acceptance import acceptance_actions
from .campaign import open_campaign, step_campaign, verify_campaign, verify_export
from .campaign_acceptance import LAST_SIGNAL
from .consumer_store import _source


class SmokeError(ValueError):
    """The real consumer process did not satisfy its gameplay contract."""


def run_smoke() -> dict:
    session = open_campaign(_source())
    choices = []
    for action in acceptance_actions("protect") + LAST_SIGNAL:
        current = verify_campaign(session)
        if action not in current["actions"]:
            raise SmokeError("canonical acceptance action not offered")
        choices.append(str(current["actions"].index(action)))
        session = step_campaign(session, action, expected_head=session["head"])
    expected_head = session["head"]
    split = max(1, len(choices) // 2)
    with tempfile.TemporaryDirectory(prefix="cinder-ridge-consumer-smoke-") as root:
        base = Path(root) / "appdata"
        base.mkdir()
        env = os.environ.copy()
        env["LOCALAPPDATA" if os.name == "nt" else "XDG_DATA_HOME"] = str(base)
        command = [sys.executable, "-m", "skeleton.game.gameplay.ridge_rescue", "consumer"]

        def invoke(args: list[str], stdin: str | None = None) -> str:
            try:
                proc = subprocess.run(
                    command + args, input=stdin, capture_output=True,
                    text=True, env=env, timeout=90,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SmokeError("consumer process could not finish") from exc
            if proc.returncode != 0:
                raise SmokeError("consumer process failed: " + proc.stderr[-300:])
            return proc.stdout

        intro = ["h", "j", "?", "not-a-command"]
        first = invoke(["play", "--slot", "smoke"], "\n".join(intro + choices[:split] + ["q"]) + "\n")
        if "Advisory only" not in first or "Unavailable command" not in first:
            raise SmokeError("interactive controls did not fail safely")
        midway = json.loads(invoke(["status", "--slot", "smoke"]))
        if midway["revision"] != split or midway["status"] != "playing":
            raise SmokeError("quit did not persist exactly the accepted turns")
        second = invoke(["play", "--slot", "smoke"], "\n".join(choices[split:] + ["q"]) + "\n")
        if "Victory:" not in second:
            raise SmokeError("restarted terminal did not show earned victory")
        final = json.loads(invoke(["status", "--slot", "smoke"]))
        if final["status"] != "completed" or final["head"] != expected_head:
            raise SmokeError("restarted campaign diverged from canonical engine")
        audit = json.loads(invoke(["audit", "--slot", "smoke"]))
        if not audit["verified"] or audit["audit_entries"] != len(choices):
            raise SmokeError("save audit did not replay all turns")
        exported = json.loads(invoke(["export", "--slot", "smoke"]))
        payload = Path(exported["path"]).read_bytes()
        if verify_export(payload)["head"] != expected_head:
            raise SmokeError("portable export failed deterministic verification")
    return {
        "schema": "ridge.rescue.consumer.process-smoke.v1",
        "result": "passed-on-current-host",
        "actions": len(choices),
        "quit_after_actions": split,
        "chapters": 2,
        "earned_head": expected_head,
        "host_windows": os.name == "nt",
        "real_processes": True,
        "portable_export_verified": True,
        "windows_device_certified": False,
        "installer_certified": False,
        "release_certified": False,
    }
