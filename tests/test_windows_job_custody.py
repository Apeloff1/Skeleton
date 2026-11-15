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

LEASE_PATH = MODULE_PATH.with_name("lease_custody.py")
lease_spec = importlib.util.spec_from_file_location("windows_lease_custody_test_target", LEASE_PATH)
assert lease_spec is not None and lease_spec.loader is not None
lease_custody = importlib.util.module_from_spec(lease_spec)
sys.modules[lease_spec.name] = lease_custody
lease_spec.loader.exec_module(lease_custody)

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
        out, error = process.communicate(timeout=3)
        assert out.strip() == b"contained" and error == b""
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


def test_workspace_marker_stays_dirty_until_job_drain(tmp_path):
    marker = tmp_path / "native.inference.lock"
    marker.write_bytes(bytes((0,)))
    fd = os.open(marker, os.O_RDWR | os.O_BINARY)
    token = lease_custody.enter_local_lease(fd)
    process = None
    try:
        process = custody.spawn_windows_job(
            [sys.executable, "-I", "-S", "-c", "import time; time.sleep(30)"],
            begin_lease_fence=lease_custody.begin_windows_native_custody,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True, shell=False,
        )
        dirty = marker.read_bytes()
        assert dirty.startswith(bytes((1,))) and len(dirty) == 33
        with pytest.raises(RuntimeError, match="already active"):
            lease_custody.begin_windows_native_custody()
        custody.terminate_windows_job(process)
        assert marker.read_bytes() == bytes((0,))
        process.communicate(timeout=3)
    finally:
        if process is not None and getattr(process, custody._JOB_ATTR).handle:
            custody.terminate_windows_job(process)
        lease_custody.leave_local_lease(token)
        os.close(fd)


def test_workspace_fence_cannot_be_cleared_by_revoked_context(tmp_path):
    marker = tmp_path / "native.inference.lock"
    marker.write_bytes(bytes((0,)))
    fd = os.open(marker, os.O_RDWR | os.O_BINARY)
    token = lease_custody.enter_local_lease(fd)
    finish = lease_custody.begin_windows_native_custody()
    lease_custody.leave_local_lease(token)
    try:
        with pytest.raises(RuntimeError, match="revoked"):
            finish()
        assert marker.read_bytes().startswith(bytes((1,))) and marker.stat().st_size == 33
    finally:
        os.close(fd)


def test_workspace_dirty_marker_refuses_new_native_fence(tmp_path):
    marker = tmp_path / "native.inference.lock"
    marker.write_bytes(bytes((1,)))
    fd = os.open(marker, os.O_RDWR | os.O_BINARY)
    token = lease_custody.enter_local_lease(fd)
    try:
        with pytest.raises(RuntimeError, match="not clean"):
            lease_custody.begin_windows_native_custody()
        assert marker.read_bytes() == bytes((1,))
    finally:
        lease_custody.leave_local_lease(token)
        os.close(fd)


def test_operator_recovery_is_bound_to_single_launch_and_evidence(tmp_path):
    marker = tmp_path / "native.inference.lock"
    marker.write_bytes(bytes((0,)))
    fd = os.open(marker, os.O_RDWR | os.O_BINARY)
    key = b"k" * 32
    evidence = "e" * 64
    try:
        token = lease_custody.enter_local_lease(fd)
        lease_custody.begin_windows_native_custody()
        lease_custody.leave_local_lease(token)
        candidate = lease_custody.windows_recovery_candidate(fd)
        approval = lease_custody.issue_windows_drain_approval(
            candidate, drain_evidence_sha256=evidence, operator_key=key,
        )
        dirty = marker.read_bytes()
        with pytest.raises(RuntimeError, match="authentication"):
            lease_custody.recover_windows_dirty_record(fd, approval=approval, operator_key=b"x" * 32)
        with pytest.raises(RuntimeError, match="authentication"):
            lease_custody.recover_windows_dirty_record(
                fd, approval={**approval, "drain_evidence_sha256": "f" * 64},
                operator_key=key,
            )
        assert marker.read_bytes() == dirty
        lease_custody.recover_windows_dirty_record(fd, approval=approval, operator_key=key)
        assert marker.read_bytes() == bytes((0,))
        token = lease_custody.enter_local_lease(fd)
        finish = lease_custody.begin_windows_native_custody()
        try:
            with pytest.raises(RuntimeError, match="current launch"):
                lease_custody.recover_windows_dirty_record(fd, approval=approval, operator_key=key)
        finally:
            finish()
            lease_custody.leave_local_lease(token)
    finally:
        os.close(fd)


def test_legacy_dirty_challenge_preparation_never_clears_marker(tmp_path):
    marker = tmp_path / "legacy.inference.lock"
    marker.write_bytes(bytes((1,)))
    fd = os.open(marker, os.O_RDWR | os.O_BINARY)
    try:
        with pytest.raises(RuntimeError, match="explicit preparation"):
            lease_custody.windows_recovery_candidate(fd)
        assert marker.read_bytes() == bytes((1,))
        candidate = lease_custody.windows_recovery_candidate(fd, prepare_legacy=True)
        assert len(marker.read_bytes()) == 33
        assert marker.read_bytes().startswith(bytes((1,)))
        assert lease_custody.windows_recovery_candidate(fd, prepare_legacy=True) == candidate
    finally:
        os.close(fd)


def test_windows_workspace_recovery_uses_same_exclusive_lock(tmp_path):
    # Load exact app lock module with the already-loaded lightweight dependency,
    # avoiding unrelated model imports on the focused Windows runner.
    dependency = "skeleton.ai.runtime.inference.lease_custody"
    old = sys.modules.get(dependency)
    sys.modules[dependency] = lease_custody
    try:
        path = MODULE_PATH.parents[3] / "app" / "jeeves_local_lease.py"
        app_spec = importlib.util.spec_from_file_location("windows_workspace_lease_test_target", path)
        assert app_spec is not None and app_spec.loader is not None
        app = importlib.util.module_from_spec(app_spec)
        app_spec.loader.exec_module(app)
    finally:
        if old is None:
            sys.modules.pop(dependency, None)
        else:
            sys.modules[dependency] = old
    owner = app.LocalInferenceLease(tmp_path / "workspace.db")
    peer = app.LocalInferenceLease(tmp_path / "workspace.db")
    with owner.hold():
        lease_custody.begin_windows_native_custody()
        with pytest.raises(app.LocalInferenceLeaseBusy):
            peer.prepare_windows_crash_recovery()
    with pytest.raises(app.LocalInferenceLeaseUnavailable, match="reconciliation"):
        with peer.hold():
            pytest.fail("dirty workspace admitted a second launch")
    candidate = peer.prepare_windows_crash_recovery()
    key = b"z" * 32
    approval = lease_custody.issue_windows_drain_approval(
        candidate, drain_evidence_sha256="d" * 64, operator_key=key,
    )
    peer.recover_windows_crash_marker(approval=approval, operator_key=key)
    with peer.hold():
        pass


def test_recovery_rejects_noncanonical_approval_without_clearing(tmp_path):
    marker = tmp_path / "authority.lock"
    marker.write_bytes(bytes((1,)) + b"a" * 32)
    fd = os.open(marker, os.O_RDWR | os.O_BINARY)
    class Hostile(str):
        def __eq__(self, other):
            raise AssertionError("untrusted equality")
    class HostileMapping(dict):
        def __eq__(self, other):
            raise AssertionError("untrusted mapping equality")
    try:
        key = b"k" * 32
        candidate = lease_custody.windows_recovery_candidate(fd)
        approval = lease_custody.issue_windows_drain_approval(
            candidate, drain_evidence_sha256="e" * 64, operator_key=key,
        )
        dirty = marker.read_bytes()
        for invalid in (
            {**approval, "candidate": HostileMapping(candidate)},
            {**approval, "candidate": {**candidate, "schema": Hostile(candidate["schema"])}},
            {**approval, "mac": "界" * 64},
        ):
            with pytest.raises((RuntimeError, ValueError)):
                lease_custody.recover_windows_dirty_record(fd, approval=invalid, operator_key=key)
            assert marker.read_bytes() == dirty
        lease_custody.recover_windows_dirty_record(fd, approval=approval, operator_key=key)
        assert marker.read_bytes() == bytes((0,))
    finally:
        os.close(fd)


@pytest.mark.parametrize("override", [
    {"executable": "other.exe"}, {"startupinfo": object()},
    {"creationflags": 0x01000000}, {"creationflags": True},
    {"start_new_session": True}, {"pass_fds": (3,)},
])
def test_launch_options_cannot_replace_or_bypass_trusted_helper(monkeypatch, override):
    def forbidden(*args, **kwargs):
        pytest.fail("job created before validating trusted launch arguments")
    monkeypatch.setattr(custody, "_WindowsJob", forbidden)
    options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE, shell=False, close_fds=True)
    options.update(override)
    with pytest.raises(custody.WindowsJobUnavailable, match="noncanonical"):
        custody.spawn_windows_job([sys.executable, "-c", "pass"], **options)


def test_successfully_drained_job_can_be_cleaned_up_twice():
    process = start("print('done', flush=True)")
    try:
        assert process.wait(timeout=10) == 0
        assert custody.terminate_windows_job(process)
        assert custody.terminate_windows_job(process)
        out, error = process.communicate(timeout=3)
        assert out.strip() == b"done" and error == b""
    finally:
        if getattr(process, custody._JOB_ATTR).handle:
            custody.terminate_windows_job(process)


def test_incomplete_prior_drain_is_not_idempotent_success():
    process = start("pass")
    job = getattr(process, custody._JOB_ATTR)
    try:
        job.stop()
        job.close()
        process.wait(timeout=5)
        with pytest.raises(custody.WindowsJobUnavailable, match="unverified"):
            custody.terminate_windows_job(process)
    finally:
        if job.handle:
            custody.terminate_windows_job(process)
        process.communicate(timeout=3)
