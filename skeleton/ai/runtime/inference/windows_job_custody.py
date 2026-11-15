"""Fail-closed Windows Job Object custody for local GGUF subprocesses.

The trusted Python helper waits on a private one-byte pipe before launching
anything. The supervisor assigns that helper to an unnamed, noninheritable,
kill-on-close job before releasing the gate. Descendants inherit membership;
breakaway is not enabled. No shell or user-supplied helper code is involved.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable

_JOB_ATTR = "_skeleton_native_job"
_FENCE_ATTR = "_skeleton_native_fence_completion"
_DRAINED_ATTR = "_skeleton_native_job_drained"
_LAUNCH_OPTIONS = frozenset({
    "stdin", "stdout", "stderr", "cwd", "env", "shell", "start_new_session",
    "close_fds", "creationflags", "bufsize",
})
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1

# -I -S isolates the trusted helper from user site, PYTHONPATH and startup
# hooks. The target command is argv, not interpolated Python source.
_GATE_PROGRAM = (
    "import subprocess,sys\n"
    "if sys.stdin.buffer.read(1) != b'\\xa5':\n"
    "    raise SystemExit(125)\n"
    "result = subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL, "
    "close_fds=True, shell=False)\n"
    "raise SystemExit(result if 0 <= result <= 255 else 1)\n"
)


class WindowsJobUnavailable(RuntimeError):
    """No verified Windows containment; native launch must not continue."""


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_int64),
        ("TotalKernelTime", ctypes.c_int64),
        ("ThisPeriodTotalUserTime", ctypes.c_int64),
        ("ThisPeriodTotalKernelTime", ctypes.c_int64),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


def _kernel():
    if os.name != "nt":
        raise WindowsJobUnavailable("Windows Job Objects unavailable")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                     wintypes.DWORD], wintypes.BOOL),
        "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        "IsProcessInJob": ([wintypes.HANDLE, wintypes.HANDLE,
                            ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                       wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes = arguments
        function.restype = result
    return kernel


class _WindowsJob:
    def __init__(self):
        self.kernel = _kernel()
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise WindowsJobUnavailable("could not create private Job Object")
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(
            self.handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits),
        ):
            self.close()
            raise WindowsJobUnavailable("kill-on-close Job Object policy unavailable")

    def attach(self, process: subprocess.Popen[bytes]) -> None:
        # CPython Popen owns the kernel process handle, avoiding PID reuse.
        handle = getattr(process, "_handle", None)
        if handle is None or not self.kernel.AssignProcessToJobObject(self.handle, int(handle)):
            raise WindowsJobUnavailable("native helper Job Object assignment denied")
        member = wintypes.BOOL()
        if not self.kernel.IsProcessInJob(int(handle), self.handle, ctypes.byref(member)) or not member.value:
            raise WindowsJobUnavailable("native helper Job Object membership unverifiable")

    def active(self) -> int:
        accounting = _Accounting()
        if not self.kernel.QueryInformationJobObject(
            self.handle, _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting), ctypes.sizeof(accounting), None,
        ):
            raise WindowsJobUnavailable("native job process inventory unavailable")
        return int(accounting.ActiveProcesses)

    def stop(self) -> None:
        # Preserve a healthy leader's return code; only stop live descendants.
        # Hold the job until the kernel reports zero active members.
        if self.active():
            if not self.kernel.TerminateJobObject(self.handle, 1):
                if self.active():
                    raise WindowsJobUnavailable("native job termination denied")
            while self.active():
                time.sleep(0.05)

    def close(self) -> None:
        if self.handle:
            if not self.kernel.CloseHandle(self.handle):
                raise WindowsJobUnavailable("native job handle close failed")
            self.handle = None


def spawn_windows_job(
    command: list[str], *, begin_lease_fence: Callable[[], Callable[[], None] | None] | None = None,
    **kwargs: Any,
) -> subprocess.Popen[bytes]:
    """Launch target only after verified job assignment; no uncontained fallback."""
    if os.name != "nt" or sys.implementation.name != "cpython" or getattr(sys, "frozen", False):
        raise WindowsJobUnavailable("trusted Windows CPython helper unavailable")
    if (
        type(command) not in (list, tuple) or not 1 <= len(command) <= 1024
        or any(type(part) is not str or "\x00" in part or len(part) > 32767 for part in command)
        or not command[0]
        or sum(len(part) for part in command) > 32767
        or not set(kwargs) <= _LAUNCH_OPTIONS
        or kwargs.get("start_new_session", False) is not False
        or type(kwargs.get("creationflags", 0)) is not int
        or kwargs.get("creationflags", 0) not in (0, subprocess.CREATE_NO_WINDOW)
        or kwargs.get("stdin") != subprocess.DEVNULL
        or kwargs.get("shell", False) is not False
        or kwargs.get("close_fds") is not True
        or not sys.executable or not Path(sys.executable).is_absolute()
    ):
        raise WindowsJobUnavailable("noncanonical native launch arguments")
    if begin_lease_fence is not None and not callable(begin_lease_fence):
        raise WindowsJobUnavailable("invalid workspace fence callback")
    # Freeze argv before creating the job or invoking any caller callback.
    command = tuple(command)
    job = _WindowsJob()
    process = None
    finish_fence = None
    try:
        if begin_lease_fence is not None:
            finish_fence = begin_lease_fence()
        options = dict(kwargs)
        options["stdin"] = subprocess.PIPE
        options["creationflags"] = options.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        process = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", _GATE_PROGRAM, *command], **options,
        )
        job.attach(process)
        if process.stdin is None:
            raise WindowsJobUnavailable("private launch gate unavailable")
        setattr(process, _JOB_ATTR, job)
        setattr(process, _FENCE_ATTR, finish_fence)
        # No GGUF command executes until assignment and membership checks succeed.
        if process.stdin.write(b"\xa5") != 1:
            raise WindowsJobUnavailable("private launch gate write incomplete")
        process.stdin.flush()
        process.stdin.close()
        process.stdin = None
        return process
    except BaseException:
        # Never clean the workspace marker on ambiguous termination. Drain
        # the assigned job before closing its handle, then reap the helper.
        # If assignment failed the unassigned helper has not received the gate.
        try:
            try:
                job.stop()
            finally:
                job.close()
            if process is not None:
                if process.stdin is not None:
                    process.stdin.close()
                    process.stdin = None
                if process.poll() is None:
                    process.kill()
                process.wait()
            if finish_fence is not None:
                finish_fence()
        finally:
            if process is not None:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
        raise


def terminate_windows_job(process: subprocess.Popen[bytes]) -> bool:
    """Drain job membership before releasing native resource custody."""
    if os.name != "nt":
        return False
    job = getattr(process, _JOB_ATTR, None)
    if type(job) is not _WindowsJob:
        raise WindowsJobUnavailable("Windows native process lacks job custody")
    if getattr(process, _DRAINED_ATTR, False) is True:
        return True
    # A previous failed drain/close is not proof of successful cleanup.
    if not job.handle:
        raise WindowsJobUnavailable("native job drainage remains unverified")
    try:
        job.stop()
    finally:
        job.close()  # kernel kill-on-close is also the supervisor-death fence
    process.wait()
    finish_fence = getattr(process, _FENCE_ATTR, None)
    if finish_fence is not None:
        finish_fence()
        setattr(process, _FENCE_ATTR, None)
    setattr(process, _DRAINED_ATTR, True)
    return True
