"""Owned POSIX process-group shutdown without premature leader reaping.

Only for children started with start_new_session=True and exclusively waited
by their spawning supervisor. WNOWAIT keeps the PID allocated until the final
group signal. No signal is sent after reaping. This is not a sandbox against
a child that deliberately escapes the process group or an external reaper.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time


def supports_group_custody() -> bool:
    return os.name == "posix" and all(
        hasattr(os, name) for name in ("waitid", "P_PID", "WEXITED", "WNOWAIT", "WNOHANG", "killpg", "getpgid", "getsid")
    )


def observe_worker_exit(process: subprocess.Popen[bytes]) -> bool:
    """Observe leader exit without consuming its wait status where supported."""
    if not supports_group_custody():
        return process.poll() is not None
    if process.returncode is not None:
        return True
    while True:
        try:
            result = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            return result is not None and result.si_pid == process.pid
        except InterruptedError:
            continue
        except ChildProcessError as exc:
            # Another waiter or SIGCHLD disposition consumed the PID.
            # The process group number is no longer ours to signal.
            raise RuntimeError("GGUF process leader no longer exclusively waitable") from exc


def _require_owned_group(process: subprocess.Popen[bytes]) -> None:
    """Require the original, unreaped session leader, not merely a live PID."""
    pid = process.pid
    if type(pid) is not int or pid <= 1 or pid == os.getpid():
        raise RuntimeError("invalid GGUF process group identity")
    if process.returncode is not None:
        raise RuntimeError("cannot signal a reaped GGUF process group")
    observe_worker_exit(process)
    try:
        group, session = os.getpgid(pid), os.getsid(pid)
    except OSError as exc:
        raise RuntimeError("GGUF process group identity unavailable") from exc
    if group != pid or session != pid:
        raise RuntimeError("GGUF process is not the owned session leader")


def _signal_group(process: subprocess.Popen[bytes], sig: int) -> None:
    # Revalidate that the leader remains waitable immediately before signalling.
    # Exclusivity of the wait owner is part of the trusted spawn contract.
    _require_owned_group(process)
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        # No live members: the owned leader is still waitable.
        pass


def terminate_owned_process_group(process: subprocess.Popen[bytes]) -> bool:
    """Signal all same-group descendants before reaping the leader.

    Return False on platforms lacking the primitive so the existing platform
    cleanup can run. A leader stuck in kernel I/O deliberately retains custody;
    a termination request is not proof of exit.
    """
    if not supports_group_custody():
        return False
    if process.returncode is not None:
        # Never reuse the PID/PGID of an already reaped leader. This means
        # no further signalling is permitted, not proof of descendant exit.
        return True
    _require_owned_group(process)
    if not observe_worker_exit(process):
        _signal_group(process, signal.SIGTERM)
        deadline = time.monotonic() + 1.0
        while not observe_worker_exit(process) and time.monotonic() < deadline:
            time.sleep(0.01)

    # A clean or terminated leader may leave descendants holding output
    # pipes and inherited lease descriptors. Always signal the whole group
    # while the leader's PID is still reserved.
    _signal_group(process, signal.SIGKILL)
    while not observe_worker_exit(process):
        time.sleep(0.25)
        _signal_group(process, signal.SIGKILL)
    process.wait()
    return True
