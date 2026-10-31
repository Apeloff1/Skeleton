"""Regression for sandbox pipe backpressure and bounded subprocess lifetime.

These checks use the isolated executor's existing network/process policy.
Only the zero-progress regression simulates a rare write syscall result.
"""
from __future__ import annotations

import os
import sys

import pytest

from skeleton.sandbox.process import ProcessLimits, run_isolated


pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process sandbox")


def _limits(seconds: float = 5.0) -> ProcessLimits:
    return ProcessLimits(
        wall_seconds=seconds,
        cpu_seconds=4,
        output_bytes=1 << 20,
        network="inherit",
    )


def test_child_ignoring_large_stdin_cannot_hold_past_wall_deadline() -> None:
    # A synchronous pipe write deadlocked until the sleeping child exited.
    result = run_isolated(
        [sys.executable, "-c", "import time; time.sleep(4)"],
        stdin=b"z" * (256 * 1024),
        limits=_limits(0.35),
    )
    assert result.timed_out
    assert result.duration_s < 3.0
    assert not result.ok


def test_full_duplex_output_before_stdin_read_cannot_deadlock() -> None:
    # Child fills its stdout pipe *before* it reads stdin; parent must read and
    # write concurrently instead of filling stdin first.
    script = (
        "import sys;"
        "sys.stdout.buffer.write(b'O' * 131072);"
        "sys.stdout.buffer.flush();"
        "data = sys.stdin.buffer.read();"
        "sys.stdout.buffer.write(b':' + str(len(data)).encode());"
        "sys.stdout.buffer.flush()"
    )
    result = run_isolated(
        [sys.executable, "-c", script],
        stdin=b"I" * 131072,
        limits=_limits(),
    )
    assert result.ok, result.to_record()
    assert not result.timed_out
    assert not result.truncated
    assert result.stdout == b"O" * 131072 + b":131072"



def test_full_duplex_stderr_before_stdin_read_cannot_deadlock() -> None:
    # Both output pipes are serviced while the bounded input is delivered.
    # A blocking stdin writer deadlocks when the child fills stderr first.
    script = (
        "import sys;"
        "sys.stderr.buffer.write(b'E' * 131072);"
        "sys.stderr.buffer.flush();"
        "data = sys.stdin.buffer.read();"
        "sys.stdout.buffer.write(str(len(data)).encode());"
        "sys.stdout.buffer.flush()"
    )
    result = run_isolated(
        [sys.executable, "-c", script],
        stdin=b"I" * 131072,
        limits=_limits(),
    )
    assert result.ok, result.to_record()
    assert not result.timed_out and not result.truncated
    assert result.stderr == b"E" * 131072
    assert result.stdout == b"131072"

def test_early_stdin_close_is_not_a_spurious_failure() -> None:
    # EPIPE is normal if the child chooses not to consume supplied data.
    result = run_isolated(
        [sys.executable, "-c", "import sys; sys.exit(0)"],
        stdin=b"I" * 131072,
        limits=_limits(),
    )
    assert result.ok, result.to_record()
    assert not result.timed_out


def test_empty_stdin_signals_eof_instead_of_hanging_child() -> None:
    result = run_isolated(
        [sys.executable, "-c", "import sys; print(len(sys.stdin.buffer.read()))"],
        stdin=b"",
        limits=_limits(),
    )
    assert result.ok, result.to_record()
    assert result.stdout.strip() == b"0"



def test_zero_byte_nonblocking_write_preserves_pending_stdin(monkeypatch) -> None:
    # A zero-byte write on a nonempty chunk is not a successful transfer.
    # Exercise the real subprocess and simulate only the rare syscall result.
    import skeleton.sandbox.process as sandbox_process

    real_write = os.write
    injected = {"used": False}

    def zero_once(fd, data):
        if not injected["used"] and len(data):
            injected["used"] = True
            return 0
        return real_write(fd, data)

    monkeypatch.setattr(sandbox_process.os, "write", zero_once)
    payload = b"preserve-pending-bytes:" * 8192
    result = run_isolated(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        stdin=payload,
        limits=_limits(),
    )
    assert injected["used"]
    assert result.ok and not result.timed_out, result.to_record()
    assert result.stdout == payload

@pytest.mark.parametrize("input_data", [b"x" * 1025, b"y" * (256 * 1024)])
def test_oversized_stdin_is_denied_before_process_spawn(input_data) -> None:
    # The old code silently cut stdin at output_bytes and reported success.
    from unittest.mock import patch

    from skeleton.sandbox.errors import ProcessPolicyError

    limits = ProcessLimits(output_bytes=1024, network="inherit")
    with patch("skeleton.sandbox.process.subprocess.Popen") as launch:
        with pytest.raises(ProcessPolicyError, match="stdin exceeds bounded process input limit"):
            run_isolated([sys.executable, "-c", "pass"], stdin=input_data, limits=limits)
    launch.assert_not_called()


def test_stdin_at_exact_input_bound_is_delivered_intact() -> None:
    data = b"I" * 8192
    result = run_isolated(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
        stdin=data,
        limits=ProcessLimits(output_bytes=len(data), network="inherit"),
    )
    assert result.ok, result.to_record()
    assert result.stdout == data
    assert not result.truncated


@pytest.mark.parametrize("invalid", ["text", 10, bytearray(b"bytes")])
def test_nonbytes_stdin_denied_without_launch(invalid) -> None:
    from unittest.mock import patch

    from skeleton.sandbox.errors import ProcessPolicyError

    with patch("skeleton.sandbox.process.subprocess.Popen") as launch:
        with pytest.raises(ProcessPolicyError, match="stdin must be bytes"):
            run_isolated([sys.executable, "-c", "pass"], stdin=invalid)
    launch.assert_not_called()


@pytest.mark.parametrize(
    "bad",
    [
        {"wall_seconds": float("nan")},
        {"wall_seconds": float("inf")},
        {"wall_seconds": -0.1},
        {"wall_seconds": True},
        {"wall_seconds": "ten"},
        {"cpu_seconds": 0},
        {"cpu_seconds": True},
        {"cpu_seconds": 3.5},
        {"memory_bytes": -1},
        {"memory_bytes": False},
        {"open_files": 0},
        {"open_files": -2},
        {"file_bytes": -1},
        {"file_bytes": 2.5},
        {"output_bytes": -1},
        {"output_bytes": True},
        {"processes": -1},
        {"processes": True},
        {"network": []},
    ],
)
def test_malformed_resource_limits_fail_closed(bad) -> None:
    from skeleton.sandbox.errors import ProcessPolicyError

    with pytest.raises(ProcessPolicyError):
        ProcessLimits(**bad)


def test_zero_output_budget_and_zero_file_budget_are_valid_restrictions() -> None:
    limits = ProcessLimits(file_bytes=0, output_bytes=0, processes=0)
    assert limits.file_bytes == limits.output_bytes == limits.processes == 0


def test_governed_process_modules_remain_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert (root / "skeleton/sandbox/process.py").read_bytes() == (
        root / "skeleton/ai/runtime/sandbox/process.py"
    ).read_bytes()
