"""Process ownership regressions; no physical GGUF qualification."""
from __future__ import annotations

import os

import pytest

from skeleton.app.jeeves_local_lease import LocalInferenceLease, LocalInferenceLeaseUnavailable
from skeleton.ai.runtime.inference import lease_custody as custody


class ForbiddenGate:
    def __enter__(self):
        raise AssertionError("inherited gate must not be acquired")

    def acquire(self, **kwargs):
        raise AssertionError("inherited gate must not be acquired")


def test_copied_process_cannot_use_or_release_native_binding(tmp_path, monkeypatch):
    lease = LocalInferenceLease(tmp_path / "process.sqlite3")
    with lease.hold():
        binding = custody._current_local_inference_lease.get()
        saved = binding.gate
        pid = os.getpid()
        binding.gate = ForbiddenGate()
        try:
            with monkeypatch.context() as patch:
                patch.setattr(custody.os, "getpid", lambda: pid + 1)
                with pytest.raises(RuntimeError, match="process identity"):
                    with custody.gguf_child_fd_scope():
                        pytest.fail("inherited process admitted")
                with pytest.raises(RuntimeError, match="process identity"):
                    custody.leave_local_lease(binding.token)
                assert binding.active
        finally:
            binding.gate = saved
        with custody.gguf_child_fd_scope():
            pass


def test_forked_workspace_object_fails_before_inherited_thread_lock(tmp_path, monkeypatch):
    lease = LocalInferenceLease(tmp_path / "fork.sqlite3")
    pid = os.getpid()
    lease._thread_gate = ForbiddenGate()
    with monkeypatch.context() as patch:
        patch.setattr(os, "getpid", lambda: pid + 1)
        assert lease.inspect()["state"] == "unavailable"
        with pytest.raises(LocalInferenceLeaseUnavailable, match="process identity"):
            with lease.hold():
                pytest.fail("inherited instance admitted")


def test_out_of_order_context_release_cannot_revoke_current_lease(tmp_path):
    fd1 = os.open(tmp_path / "one", os.O_CREAT | os.O_RDWR, 0o600)
    fd2 = os.open(tmp_path / "two", os.O_CREAT | os.O_RDWR, 0o600)
    outer = custody.enter_local_lease(fd1)
    inner = None
    try:
        inner = custody.enter_local_lease(fd2)
        with pytest.raises(RuntimeError, match="token"):
            custody.leave_local_lease(outer)
        with custody.gguf_child_fd_scope() as fds:
            if os.name == "posix":
                assert fds == (fd2,)
        custody.leave_local_lease(inner)
        inner = None
        with custody.gguf_child_fd_scope() as fds:
            if os.name == "posix":
                assert fds == (fd1,)
    finally:
        if inner is not None:
            custody.leave_local_lease(inner)
        custody.leave_local_lease(outer)
        os.close(fd1)
        os.close(fd2)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner mode verification")
def test_permission_change_after_os_lock_cannot_authorize_generation(tmp_path, monkeypatch):
    lease = LocalInferenceLease(tmp_path / "mode.sqlite3")
    original = lease._lock_fd

    def changed(fd):
        original(fd)
        os.fchmod(fd, 0o644)

    monkeypatch.setattr(lease, "_lock_fd", changed)
    with pytest.raises(LocalInferenceLeaseUnavailable, match="permissions"):
        with lease.hold():
            pytest.fail("unsafe marker admitted after mode change")
    assert lease.inspect()["state"] == "unavailable"


def test_marker_initializes_only_under_kernel_lock(tmp_path, monkeypatch):
    lease = LocalInferenceLease(tmp_path / "initialization.sqlite3")
    lease.path.touch(mode=0o600)
    original = lease._lock_fd

    def checked(fd):
        assert os.fstat(fd).st_size == 0
        original(fd)

    monkeypatch.setattr(lease, "_lock_fd", checked)
    with lease.hold():
        assert os.fstat(custody._current_local_inference_lease.get().fd).st_size == 1


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor owner permissions")
def test_native_launch_rechecks_marker_permissions(tmp_path):
    lease = LocalInferenceLease(tmp_path / "launch-mode.sqlite3")
    with lease.hold():
        lease.path.chmod(0o644)
        try:
            with pytest.raises(RuntimeError, match="identity changed"):
                with custody.gguf_child_fd_scope():
                    pytest.fail("native launch admitted unsafe permissions")
        finally:
            lease.path.chmod(0o600)
