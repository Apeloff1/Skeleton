"""Real subprocess regressions for POSIX group termination.

These use Python children, not GGUF weights or live GPU qualification.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest

from skeleton.ai.runtime.inference.process_group_custody import (
    observe_worker_exit, supports_group_custody, terminate_owned_process_group,
)

pytestmark = pytest.mark.skipif(
    not supports_group_custody(), reason="POSIX non-reaping waitid required",
)


def spawn(source):
    return subprocess.Popen(
        [sys.executable, "-c", source],
        start_new_session=True, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def wait_observed(process):
    deadline = time.monotonic() + 5
    while not observe_worker_exit(process):
        if time.monotonic() >= deadline:
            pytest.fail("leader did not exit")
        time.sleep(0.01)


def test_exited_leader_with_inherited_pipe_is_cleaned_before_reap():
    process = spawn(
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(12)']);"
        "print('leader done',flush=True)"
    )
    try:
        wait_observed(process)
        assert process.returncode is None
        assert terminate_owned_process_group(process)
        out, err = process.communicate(timeout=3)
        assert out == b"leader done\n"
        assert err == b""
        assert process.returncode == 0
    finally:
        if process.returncode is None:
            terminate_owned_process_group(process)
        process.communicate(timeout=15)


def test_live_group_leader_is_reaped_after_termination():
    process = spawn("import time; time.sleep(12)")
    try:
        assert terminate_owned_process_group(process)
        assert process.returncode in (-signal.SIGTERM, -signal.SIGKILL)
        process.communicate(timeout=3)
    finally:
        if process.returncode is None:
            terminate_owned_process_group(process)


def test_already_reaped_process_is_never_signalled(monkeypatch):
    process = spawn("pass")
    process.communicate(timeout=5)
    def forbidden(*args):
        pytest.fail("attempted signal using already-reaped numeric process ID")
    monkeypatch.setattr(os, "killpg", forbidden)
    assert terminate_owned_process_group(process)
