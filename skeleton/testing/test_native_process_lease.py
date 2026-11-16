"""Native lease regressions; helper subprocess is not a model runtime."""
from __future__ import annotations

from contextvars import copy_context
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from skeleton.ai.runtime.inference.lease_custody import (
    enter_local_lease, leave_local_lease, gguf_child_pass_fds,
)
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel
from skeleton.app.offline_native_process_lease import NativeCpuLeaseOwner, NativeLeaseError


pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


def private_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "native-slot"
    directory.mkdir(mode=0o700)
    return directory.resolve()


def test_context_copy_revoked_at_scope_exit(tmp_path):
    with (tmp_path / "outer.lock").open("wb") as outer:
        token = enter_local_lease(outer.fileno())
        copied = copy_context()
        assert copied.run(gguf_child_pass_fds) == (outer.fileno(),)
        leave_local_lease(token)
        assert gguf_child_pass_fds() == ()
        with pytest.raises(ValueError, match="scope has ended"):
            copied.run(gguf_child_pass_fds)


def test_reused_numeric_descriptor_refused(tmp_path):
    fd = os.open(tmp_path / "original", os.O_WRONLY | os.O_CREAT, 0o600)
    replacement = os.open(tmp_path / "replacement", os.O_WRONLY | os.O_CREAT, 0o600)
    token = enter_local_lease(fd)
    try:
        os.dup2(replacement, fd)
        with pytest.raises(ValueError, match="identity changed"):
            gguf_child_pass_fds()
    finally:
        leave_local_lease(token)
        os.close(fd)
        os.close(replacement)


def test_nested_scopes_reject_out_of_order_leave(tmp_path):
    with (tmp_path / "first").open("wb") as first, (tmp_path / "second").open("wb") as second:
        a = enter_local_lease(first.fileno())
        b = enter_local_lease(second.fileno())
        try:
            with pytest.raises(ValueError, match="LIFO"):
                leave_local_lease(a)
            assert gguf_child_pass_fds() == (second.fileno(),)
        finally:
            leave_local_lease(b)
            assert gguf_child_pass_fds() == (first.fileno(),)
            leave_local_lease(a)


def test_same_inode_contention_and_recheck_after_lock(tmp_path):
    directory = private_directory(tmp_path)
    checks = []
    first = NativeCpuLeaseOwner(directory, lambda: checks.append("first"))
    other = NativeCpuLeaseOwner(directory, lambda: checks.append("other"))
    lease = first.acquire()
    try:
        with pytest.raises(NativeLeaseError, match="already held"):
            other.acquire()
        assert checks == ["first"]
        assert first.status()["owned_parent_references"] == 1
        assert other.status()["denied"] == 1
    finally:
        lease()
        lease()
    with pytest.raises(NativeLeaseError, match="no longer matches"):
        lease.child_pass_fds()
    assert first.status()["released"] == 1
    second = other.acquire()
    second()
    assert checks == ["first", "other"]


def test_child_keeps_kernel_slot_after_parent_reference_is_closed(tmp_path):
    directory = private_directory(tmp_path)
    first = NativeCpuLeaseOwner(directory, lambda: None)
    other = NativeCpuLeaseOwner(directory, lambda: None)
    lease = first.acquire()
    child = None
    try:
        fd, = lease.child_pass_fds()
        # A trivial real Python child verifies descriptor inheritance, then
        # blocks on a pipe. This is not a llama.cpp process or model test.
        child = subprocess.Popen(
            [sys.executable, "-c", "import os,sys; os.fstat(int(sys.argv[1])); print('ready',flush=True); sys.stdin.read(1)", str(fd)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            pass_fds=(fd,), close_fds=True,
        )
        ready = threading.Event()
        lines = []
        def read():
            lines.append(child.stdout.readline())
            ready.set()
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        assert ready.wait(5) and lines == [b"ready\n"]
        lease()
        assert first.status()["owned_parent_references"] == 0
        with pytest.raises(NativeLeaseError, match="already held"):
            other.acquire()
        child.communicate(input=b"x", timeout=5)
        assert child.returncode == 0
        competitor = other.acquire()
        competitor()
    finally:
        lease()
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate(timeout=5)


def test_failed_resource_recheck_releases_slot(tmp_path):
    directory = private_directory(tmp_path)
    def denied():
        raise ValueError("critical resource pressure")
    first = NativeCpuLeaseOwner(directory, denied)
    with pytest.raises(ValueError, match="critical"):
        first.acquire()
    assert first.status()["acquired"] == 0
    assert first.status()["denied"] == 1
    other = NativeCpuLeaseOwner(directory, lambda: None)
    other.acquire()()


def test_lock_replacement_is_detected_after_activation(tmp_path):
    directory = private_directory(tmp_path)
    owner = NativeCpuLeaseOwner(directory, lambda: None)
    owner.acquire()()
    lock = directory / owner.LOCK_NAME
    replacement = directory / "replacement"
    replacement.touch(mode=0o600)
    replacement.replace(lock)
    with pytest.raises(NativeLeaseError, match="inode changed"):
        owner.acquire()


def test_private_directory_and_symlink_policy(tmp_path):
    directory = private_directory(tmp_path)
    directory.chmod(0o755)
    with pytest.raises(NativeLeaseError, match="private"):
        NativeCpuLeaseOwner(directory, lambda: None)
    directory.chmod(0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    with pytest.raises(NativeLeaseError, match="canonical"):
        NativeCpuLeaseOwner(alias, lambda: None)


def test_recovery_keeps_live_children_and_failed_releases_accounted():
    # Construct only the custody state; no actual model or process launch.
    model = object.__new__(LlamaCppModel)
    model._process_lock = threading.Lock()
    model._cleanup_recovery_lock = threading.Lock()
    model._active_processes = {17}
    model._draining_processes = {17}
    model._processes_exited = 0
    state = {"returncode": None, "pump": True, "release_failure": True}
    process = SimpleNamespace(poll=lambda: state["returncode"], stdout=None, stderr=None)
    pump = SimpleNamespace(is_alive=lambda: state["pump"])
    releases = []
    def release():
        if state["release_failure"]:
            raise NativeLeaseError("release not confirmed")
        releases.append(True)
    model._unconfirmed_cleanup = {17: (process, (pump,), release)}
    assert model.reap_unconfirmed_cleanup() == {"reaped": 0, "remaining": 1}
    state["returncode"] = 0
    assert model.reap_unconfirmed_cleanup() == {"reaped": 0, "remaining": 1}
    state["pump"] = False
    assert model.reap_unconfirmed_cleanup() == {"reaped": 0, "remaining": 1}
    state["release_failure"] = False
    assert model.reap_unconfirmed_cleanup() == {"reaped": 1, "remaining": 0}
    assert model._processes_exited == 1 and releases == [True]
    assert not model._active_processes and not model._draining_processes
    assert model.reap_unconfirmed_cleanup() == {"reaped": 0, "remaining": 0}
