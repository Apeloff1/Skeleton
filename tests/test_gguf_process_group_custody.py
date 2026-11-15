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


def test_unowned_session_is_not_signalled(monkeypatch):
    # A regular child in the test runner's own session must never cause
    # a group signal. The actual signal function is also fenced in the test.
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(12)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    def forbidden(*args):
        pytest.fail("attempted signal without owned session proof")
    monkeypatch.setattr(os, "killpg", forbidden)
    try:
        with pytest.raises(RuntimeError, match="owned session leader"):
            terminate_owned_process_group(process)
        assert process.poll() is None
    finally:
        process.kill()
        process.wait(timeout=5)


def test_session_identity_is_rechecked_at_each_signal(monkeypatch):
    process = spawn("import time; time.sleep(12)")
    real_getsid = os.getsid
    observations = 0
    def changed(pid):
        nonlocal observations
        observations += 1
        return real_getsid(pid) if observations == 1 else pid + 1
    def forbidden(*args):
        pytest.fail("group signal followed a failed identity check")
    monkeypatch.setattr(os, "getsid", changed)
    monkeypatch.setattr(os, "killpg", forbidden)
    try:
        with pytest.raises(RuntimeError, match="owned session leader"):
            terminate_owned_process_group(process)
    finally:
        process.kill()
        process.communicate(timeout=5)
