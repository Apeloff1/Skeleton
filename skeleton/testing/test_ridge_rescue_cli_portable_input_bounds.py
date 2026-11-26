"""Consumer CLI rejects hostile portable input before changing any save slot.

These subprocess checks exercise the published CLI boundary; they do not
constitute Windows device qualification.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_store import MAX_EXPORT_BYTES

MODULE = "skeleton.game.gameplay.ridge_rescue.consumer_cli"
REPO = Path(__file__).resolve().parents[2]


def invoke(root: Path, *args: str, payload: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ)
    env["XDG_DATA_HOME"] = str(root / "data")
    env["PYTHONPATH"] = str(REPO)
    return subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        input=payload,
        cwd=REPO,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=45,
        check=False,
    )


def successful(result: subprocess.CompletedProcess[bytes]) -> dict:
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("verify-export", b""),
        ("verify-export", b"{"),
        ("verify-export", b"[]"),
        ("verify-export", b"null"),
        ("verify-backup", b""),
        ("verify-backup", b"not-json"),
        ("restore", b"{"),
        ("restore-backup", b"[]"),
    ],
)
def test_invalid_portable_input_fails_without_mutating_save(tmp_path, command, payload):
    original = successful(invoke(tmp_path, "new", "--slot", "preserve"))
    failed = invoke(tmp_path, command, "--slot", "preserve", "--file", "-", payload=payload)
    assert failed.returncode != 0
    assert b"Traceback" not in failed.stderr
    current = successful(invoke(tmp_path, "status", "--slot", "preserve"))
    assert current["head"] == original["head"]
    assert current["revision"] == 0
    audit = successful(invoke(tmp_path, "audit", "--slot", "preserve"))
    assert audit["head"] == original["head"]


@pytest.mark.parametrize("command", ["verify-export", "verify-backup", "restore", "restore-backup"])
def test_oversized_piped_input_is_rejected_before_parsing(tmp_path, command):
    initial = successful(invoke(tmp_path, "new", "--slot", "preserve"))
    result = invoke(
        tmp_path, command, "--slot", "preserve", "--file", "-",
        payload=b"x" * (MAX_EXPORT_BYTES + 1),
    )
    assert result.returncode == 2
    assert b"byte budget" in result.stderr
    assert b"Traceback" not in result.stderr
    assert successful(invoke(tmp_path, "status", "--slot", "preserve"))["head"] == initial["head"]


def test_verified_export_round_trip_does_not_modify_original_slot(tmp_path):
    initial = successful(invoke(tmp_path, "new", "--slot", "preserve"))
    exported = successful(invoke(tmp_path, "export", "--slot", "preserve"))
    artifact = Path(exported["path"])
    payload = artifact.read_bytes()
    result = successful(invoke(tmp_path, "verify-export", "--file", "-", payload=payload))
    assert result["verified"] is True
    assert result["head"] == initial["head"]
    restored = successful(invoke(tmp_path, "restore", "--slot", "copy", "--file", "-", payload=payload))
    assert restored["head"] == initial["head"]
    assert successful(invoke(tmp_path, "status", "--slot", "preserve"))["head"] == initial["head"]
    assert successful(invoke(tmp_path, "audit", "--slot", "copy"))["verified"] is True


def test_failed_restore_does_not_create_destination_slot(tmp_path):
    failed = invoke(tmp_path, "restore", "--slot", "destination", "--file", "-", payload=b"{}")
    assert failed.returncode != 0
    missing = invoke(tmp_path, "status", "--slot", "destination")
    assert missing.returncode != 0
    assert b"Traceback" not in missing.stderr
