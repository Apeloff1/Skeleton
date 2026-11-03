"""Cross-process consumer acceptance for the original Cinder Ridge game.

Source mode runs the checkout launcher. Portable mode executes a freshly
verified, self-contained zipapp from a different working directory with no
PYTHONPATH. Both modes exercise the *same* canonical action sequence and
persistent SQLite slot through separate Python processes.

Neither mode certifies a Windows device, installer, or production release.
"""
from __future__ import annotations

import hashlib
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
from .consumer_bundle import _windows_launcher


class SmokeError(ValueError):
    """The real consumer process did not satisfy its gameplay contract."""


def _choices() -> tuple[list[str], str]:
    """Derive numbered inputs from the canonical engine, not a scripted win."""
    session = open_campaign(_source())
    choices: list[str] = []
    for action in acceptance_actions("protect") + LAST_SIGNAL:
        current = verify_campaign(session)
        if action not in current["actions"]:
            raise SmokeError("canonical acceptance action not offered")
        choices.append(str(current["actions"].index(action)))
        session = step_campaign(session, action, expected_head=session["head"])
    completed = verify_campaign(session)
    if completed["status"] != "completed" or completed["index"] != 2:
        raise SmokeError("source campaign did not earn both endings")
    return choices, session["head"]


def _invoke(command: list[str], args: list[str], *, env: dict[str, str],
            cwd: Path, stdin: str | None = None, expect_success: bool = True) -> str:
    try:
        proc = subprocess.run(
            command + args, input=stdin, capture_output=True, text=True,
            cwd=str(cwd), env=env, timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SmokeError("consumer process could not finish") from exc
    if expect_success and proc.returncode != 0:
        raise SmokeError("consumer process failed: " + proc.stderr[-300:])
    if not expect_success and proc.returncode == 0:
        raise SmokeError("invalid consumer command unexpectedly succeeded")
    return proc.stdout if expect_success else proc.stderr


def _smoke(command: list[str], *, root: Path, portable: bool) -> dict:
    choices, expected_head = _choices()
    split = max(1, len(choices) // 2)
    base = root / "appdata"
    base.mkdir()
    env = os.environ.copy()
    env["LOCALAPPDATA" if os.name == "nt" else "XDG_DATA_HOME"] = str(base)
    env["PYTHONUTF8"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    if portable:
        # A checkout or editable installation must not be needed by the game.
        env["PYTHONPATH"] = ""
    else:
        # The source smoke deliberately runs from a disposable working dir.
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[4])
    first = _invoke(
        command, ["play", "--slot", "smoke", "--ascii"], env=env, cwd=root,
        stdin="\n".join(["h", "j", "?", "b", "not-a-command", "9" * 5000,
                             "1" * 128, "١"] + choices[:split] + ["q"]) + "\n",
    )
    if ("Advisory only" not in first or "Unavailable command" not in first or
        "Backup created:" not in first):
        raise SmokeError("interactive controls did not fail safely")
    midway = json.loads(_invoke(command, ["status", "--slot", "smoke"], env=env, cwd=root))
    if midway["revision"] != split or midway["status"] != "playing":
        raise SmokeError("quit did not persist exactly the accepted turns")
    if midway["head"] == expected_head:
        raise SmokeError("midway save incorrectly claimed completed head")
    # Restore a mid-campaign checkpoint in a new process, then independently
    # finish that save to prove portable restoration is playable, not cosmetic.
    partial = json.loads(_invoke(command, ["export", "--slot", "smoke"], env=env, cwd=root))
    partial_payload = Path(partial["path"]).read_bytes()
    resumed_mid = json.loads(_invoke(
        command, ["restore", "--slot", "recovered-mid", "--file", "-"],
        env=env, cwd=root, stdin=partial_payload.decode("utf-8"),
    ))
    if resumed_mid["head"] != midway["head"] or resumed_mid["revision"] != split:
        raise SmokeError("partial portable restore lost the playable checkpoint")
    second = _invoke(
        command, ["play", "--slot", "smoke", "--ascii"], env=env, cwd=root,
        stdin="\n".join(choices[split:] + ["q"]) + "\n",
    )
    if "Victory:" not in second:
        raise SmokeError("restarted terminal did not show earned victory")
    final = json.loads(_invoke(command, ["status", "--slot", "smoke"], env=env, cwd=root))
    if final["status"] != "completed" or final["head"] != expected_head:
        raise SmokeError("restarted campaign diverged from canonical engine")
    if final["revision"] != len(choices):
        raise SmokeError("game saved a different number of accepted turns")
    resumed_play = _invoke(
        command, ["play", "--slot", "recovered-mid", "--ascii"], env=env, cwd=root,
        stdin="\n".join(choices[split:] + ["q"]) + "\n",
    )
    if "Victory:" not in resumed_play:
        raise SmokeError("restored checkpoint did not earn an ending")
    resumed_final = json.loads(_invoke(
        command, ["status", "--slot", "recovered-mid"], env=env, cwd=root,
    ))
    if resumed_final["head"] != expected_head or resumed_final["revision"] != len(choices):
        raise SmokeError("restored checkpoint diverged during resumed gameplay")
    resumed_audit = json.loads(_invoke(
        command, ["audit", "--slot", "recovered-mid"], env=env, cwd=root,
    ))
    if not resumed_audit["verified"] or resumed_audit["audit_entries"] != len(choices):
        raise SmokeError("restored checkpoint action history failed audit")
    audit = json.loads(_invoke(command, ["audit", "--slot", "smoke"], env=env, cwd=root))
    if not audit["verified"] or audit["audit_entries"] != len(choices):
        raise SmokeError("save audit did not replay all turns")
    exported = json.loads(_invoke(command, ["export", "--slot", "smoke"], env=env, cwd=root))
    export_path = Path(exported["path"])
    if not export_path.is_file() or not export_path.is_relative_to(base):
        raise SmokeError("export escaped disposable consumer data directory")
    payload = export_path.read_bytes()
    restored = verify_export(payload)
    if restored["head"] != expected_head or restored["status"] != "completed":
        raise SmokeError("portable export failed deterministic verification")
    verified_pipe = json.loads(_invoke(
        command, ["verify-export", "--file", "-"], env=env, cwd=root,
        stdin=payload.decode("utf-8"),
    ))
    if not verified_pipe["verified"] or verified_pipe["head"] != expected_head:
        raise SmokeError("bounded cross-platform export verification failed")
    # Restore the exported campaign through a new real consumer process and
    # require an independently replayed, complete transactional audit.
    restored_slot = json.loads(_invoke(
        command, ["restore", "--slot", "restored", "--file", "-"],
        env=env, cwd=root, stdin=payload.decode("utf-8"),
    ))
    if restored_slot["head"] != expected_head or restored_slot["revision"] != len(choices):
        raise SmokeError("portable restore diverged from the earned game")
    restored_audit = json.loads(_invoke(
        command, ["audit", "--slot", "restored"], env=env, cwd=root,
    ))
    if not restored_audit["verified"] or restored_audit["audit_entries"] != len(choices):
        raise SmokeError("restored save does not have complete replay custody")
    rejected_restore = _invoke(
        command, ["restore", "--slot", "restored", "--file", "-"],
        env=env, cwd=root, stdin=payload.decode("utf-8"), expect_success=False,
    )
    if "already exists" not in rejected_restore:
        raise SmokeError("restoration did not reject existing slot overwrite")
    damaged = bytearray(payload)
    damaged[-2] ^= 1
    _invoke(command, ["restore", "--slot", "tampered", "--file", "-"],
            env=env, cwd=root, stdin=damaged.decode("utf-8", errors="replace"),
            expect_success=False)
    # A versioned full-history backup must survive a separate-process restore,
    # including its exact action ledger, without replacing any existing slot.
    backup = json.loads(_invoke(command, ["backup", "--slot", "smoke"], env=env, cwd=root))
    backup_payload = Path(backup["path"]).read_bytes()
    verified_backup = json.loads(_invoke(
        command, ["verify-backup", "--file", "-"], env=env, cwd=root,
        stdin=backup_payload.decode("utf-8"),
    ))
    if not verified_backup["verified"] or verified_backup["head"] != expected_head:
        raise SmokeError("portable backup verification failed")
    backup_restored = json.loads(_invoke(
        command, ["restore-backup", "--slot", "backup-restored", "--file", "-"],
        env=env, cwd=root, stdin=backup_payload.decode("utf-8"),
    ))
    if backup_restored["head"] != expected_head or backup_restored["revision"] != len(choices):
        raise SmokeError("full-history backup restoration diverged")
    backup_audit = json.loads(_invoke(
        command, ["audit", "--slot", "backup-restored"], env=env, cwd=root,
    ))
    if not backup_audit["verified"] or backup_audit["audit_entries"] != len(choices):
        raise SmokeError("restored backup action history is incomplete")
    # A rejected mutation must not damage the earned save or append history.
    invalid = _invoke(
        command, ["step", "--slot", "smoke", "--action", '{"verb":"fly"}',
                  "--expected-head", expected_head], env=env, cwd=root,
        expect_success=False,
    )
    if "completed" not in invalid and "unavailable" not in invalid:
        raise SmokeError("invalid post-victory transition failed for unexpected reason")
    stable = json.loads(_invoke(command, ["status", "--slot", "smoke"], env=env, cwd=root))
    if stable["head"] != expected_head or stable["revision"] != len(choices):
        raise SmokeError("rejected mutation altered earned game state")
    return {
        "schema": "ridge.rescue.consumer.process-smoke.v2",
        "result": "passed-on-current-host",
        "actions": len(choices),
        "quit_after_actions": split,
        "chapters": 2,
        "earned_head": expected_head,
        "host_windows": os.name == "nt",
        "real_processes": True,
        "portable_export_verified": True,
        "portable_restore_audited": True,
        "partial_restore_resume_verified": True,
        "stdin_export_verification": True,
        "full_history_backup_restored": True,
        "restore_overwrite_rejected": True,
        "tampered_restore_rejected": True,
        "invalid_mutation_rejected": True,
        "portable_zipapp_verified": portable,
        "windows_device_certified": False,
        "installer_certified": False,
        "release_certified": False,
    }


def run_smoke() -> dict:
    """Test the source-checkout consumer entrypoint across real processes."""
    with tempfile.TemporaryDirectory(prefix="cinder-ridge-source-smoke-") as folder:
        return _smoke(
            [sys.executable, "-m", "skeleton.game.gameplay.ridge_rescue",
             "consumer"], root=Path(folder), portable=False,
        )


def run_portable_smoke() -> dict:
    """Build and execute the original zipapp outside the source checkout.

    The artifact is created only in an isolated temporary directory. No
    installed game or user save is modified. Native Windows qualification
    still requires executing this command on a target Windows laptop.
    """
    from .consumer_bundle import build_bytes, verify_bytes
    archive = build_bytes()
    metadata = verify_bytes(archive)
    with tempfile.TemporaryDirectory(prefix="cinder-ridge-portable-smoke-") as folder:
        root = Path(folder)
        artifact = root / "cinder-ridge.pyz"
        with artifact.open("xb") as handle:
            handle.write(archive)
            handle.flush()
            os.fsync(handle.fileno())
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != metadata["sha256"]:
            raise SmokeError("portable archive changed during publication")
        # -I excludes PYTHONPATH, user site, and current-directory imports.
        # The portable archive must run from its own bundled source only.
        result = _smoke([sys.executable, "-I", str(artifact)], root=root, portable=True)
        launcher = root / "launch-cinder-ridge.cmd"
        launcher.write_bytes(_windows_launcher(artifact.name))
        if b" -I " not in launcher.read_bytes():
            raise SmokeError("Windows launcher did not isolate Python imports")
        if os.name == "nt":
            choices, _ = _choices()
            launcher_env = os.environ.copy()
            launcher_env["LOCALAPPDATA"] = str(root / "windows-launcher-data")
            launcher_env["PYTHONPATH"] = str(root / "poisoned-import-path")
            launcher_env["PYTHONUTF8"] = "1"
            launcher_env["PYTHONNOUSERSITE"] = "1"
            output = _invoke(
                ["cmd.exe", "/d", "/c", str(launcher)], [],
                env=launcher_env, cwd=root,
                stdin="\\n".join(choices + ["q"]) + "\\n",
            )
            if "Victory:" not in output:
                raise SmokeError("Windows launcher did not earn an ending")
    return {
        **result,
        "archive_sha256": metadata["sha256"],
        "archive_files": metadata["files"],
        "source_checkout_dependency": False,
    }
