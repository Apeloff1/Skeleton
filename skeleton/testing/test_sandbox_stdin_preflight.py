"""Fail-closed stdin admission regression for mirrored POSIX process sandboxes."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.sandbox.errors import ProcessPolicyError
from skeleton.sandbox.process import ProcessLimits, run_isolated


pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX sandbox only")


@pytest.mark.parametrize("stdin", [b"Z" * 1025, b"Q" * (128 * 1024)])
def test_oversized_stdin_does_not_launch_process(stdin: bytes) -> None:
    limits = ProcessLimits(output_bytes=1024, network="inherit")
    with patch("skeleton.sandbox.process.subprocess.Popen") as launch:
        with pytest.raises(ProcessPolicyError, match="stdin exceeds bounded process input limit"):
            run_isolated([sys.executable, "-c", "pass"], stdin=stdin, limits=limits)
        launch.assert_not_called()


@pytest.mark.parametrize("stdin", ["hello", 7, bytearray(b"mutable")])
def test_nonbytes_stdin_is_rejected_prelaunch(stdin: object) -> None:
    with patch("skeleton.sandbox.process.subprocess.Popen") as launch:
        with pytest.raises(ProcessPolicyError, match="stdin must be bytes"):
            run_isolated([sys.executable, "-c", "pass"], stdin=stdin)
        launch.assert_not_called()


def test_exact_bound_stdin_is_passed_intact() -> None:
    payload = b"Hello sandbox bytes" * 128
    result = run_isolated(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        stdin=payload,
        limits=ProcessLimits(output_bytes=len(payload), wall_seconds=5, network="inherit"),
    )
    assert result.ok, result.to_record()
    assert result.stdout == payload
    assert not result.truncated


def test_mirror_modules_stay_byte_identical() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "skeleton/sandbox/process.py").read_bytes() == (
        root / "skeleton/ai/runtime/sandbox/process.py"
    ).read_bytes()
