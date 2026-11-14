"""Windows kernel Job Object tests; not real-model or installer qualification."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

# Load the dependency-free custody module itself, without importing optional
# inference providers on this deliberately focused OS test runner.
MODULE_PATH = Path(__file__).resolve().parents[1] / "skeleton/ai/runtime/inference/windows_job_custody.py"
spec = importlib.util.spec_from_file_location("windows_job_custody_test_target", MODULE_PATH)
assert spec is not None and spec.loader is not None
custody = importlib.util.module_from_spec(spec)
spec.loader.exec_module(custody)

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows kernel Job Objects required")


def start(source, *args):
    return custody.spawn_windows_job(
        [sys.executable, "-I", "-S", "-c", source, *map(str, args)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        close_fds=True, shell=False,
    )


def test_success_preserves_exit_and_output():
    process = start("print('contained', flush=True)")
    try:
        assert process.wait(timeout=10) == 0
        assert custody.terminate_windows_job(process)
        assert process.communicate(timeout=3) == (b"contained\r\n", b"")
    finally:
        if process.returncode is None:
            custody.terminate_windows_job(process)


def test_assignment_failure_never_releases_model_gate(tmp_path, monkeypatch):
    marker = tmp_path / "unexpected"
    def deny(self, process):
        raise custody.WindowsJobUnavailable("test assignment denied")
    monkeypatch.setattr(custody._WindowsJob, "attach", deny)
    with pytest.raises(custody.WindowsJobUnavailable, match="assignment denied"):
        start("import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", marker)
    assert not marker.exists()


def test_exited_helper_with_live_descendant_releases_pipes():
    process = start(
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-I','-S','-c','import time; time.sleep(30)']);"
        "print('done',flush=True)"
    )
    try:
        assert process.wait(timeout=10) == 0
        assert custody.terminate_windows_job(process)
        out, error = process.communicate(timeout=3)
        assert out.strip() == b"done" and not error
    finally:
        if getattr(process, custody._JOB_ATTR).handle:
            custody.terminate_windows_job(process)


def test_supervisor_death_kills_job_members(tmp_path):
    ready = tmp_path / "pid.txt"
    supervisor_source = (
        "import importlib.util,subprocess,sys,time\n"
        "s=importlib.util.spec_from_file_location('custody',sys.argv[1])\n"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
        "p=m.spawn_windows_job([sys.executable,'-I','-S','-c',"
        "'import os,pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(30)',"
        "sys.argv[2]], stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
        "stderr=subprocess.DEVNULL,close_fds=True,shell=False)\n"
        "time.sleep(30)\n"
    )
    supervisor = subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", supervisor_source, str(MODULE_PATH), str(ready)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    handle = None
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() or not ready.read_text().strip():
            assert supervisor.poll() is None, "gated supervisor exited"
            assert time.monotonic() < deadline, "native process did not start"
            time.sleep(0.05)
        handle = kernel.OpenProcess(0x00100001, False, int(ready.read_text()))
        assert handle
        supervisor.kill()
        supervisor.wait(timeout=5)
        assert kernel.WaitForSingleObject(handle, 5000) == 0
    finally:
        if supervisor.poll() is None:
            supervisor.kill()
        supervisor.communicate(timeout=5)
        if handle:
            if kernel.WaitForSingleObject(handle, 0) != 0:
                kernel.TerminateProcess(handle, 1)
            kernel.CloseHandle(handle)
