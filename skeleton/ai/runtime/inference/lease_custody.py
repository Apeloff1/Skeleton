"""Kernel lease custody for locally spawned GGUF workers.

A POSIX flock belongs to an open file description. Native children inherit
that exact description, never an arbitrary recycled descriptor. Context
copies share revocation state and subprocess admission is serialized against
lease exit. A Windows durable dirty marker fences replacement supervisors until
job drainage has been proved.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
import os
import stat
from threading import RLock
from typing import Callable, Iterator


@dataclass
class _LeaseBinding:
    fd: int
    device: int
    inode: int
    active: bool = True
    gate: RLock = field(default_factory=RLock)
    windows_fence: object | None = None


_current_local_inference_lease: ContextVar[_LeaseBinding | None] = ContextVar(
    "skeleton_local_gguf_lease", default=None,
)


def enter_local_lease(fd: int) -> Token[_LeaseBinding | None]:
    if type(fd) is not int or fd < 0:
        raise ValueError("invalid local inference lease descriptor")
    meta = os.fstat(fd)
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
        raise ValueError("invalid local inference lease identity")
    return _current_local_inference_lease.set(_LeaseBinding(fd, meta.st_dev, meta.st_ino))


def leave_local_lease(token: Token[_LeaseBinding | None]) -> None:
    binding = _current_local_inference_lease.get()
    if binding is None:
        raise RuntimeError("local inference lease context missing")
    with binding.gate:
        binding.active = False
        _current_local_inference_lease.reset(token)


def _verified_fds(binding: _LeaseBinding) -> tuple[int, ...]:
    if not binding.active:
        raise RuntimeError("local inference lease context revoked")
    meta = os.fstat(binding.fd)
    if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
            or (meta.st_dev, meta.st_ino) != (binding.device, binding.inode)):
        raise RuntimeError("local inference lease descriptor identity changed")
    return (binding.fd,)


@contextmanager
def gguf_child_fd_scope() -> Iterator[tuple[int, ...]]:
    """Hold admission across Popen, preventing revocation-before-inheritance."""
    binding = _current_local_inference_lease.get()
    if binding is None:
        yield ()
        return
    with binding.gate:
        if not binding.active:
            raise RuntimeError("local inference lease context revoked")
        verified = _verified_fds(binding)
        yield verified if os.name == "posix" else ()


def begin_windows_native_custody() -> Callable[[], None] | None:
    """Persist a dirty marker *before* permitting a Windows native launch.

    Only the returned completion callback may clean this particular fence.
    Call it after verified zero job membership and helper reaping, never
    merely because a termination request was sent. On crash, leave the
    marker dirty; a replacement supervisor cannot assume the job has drained.
    Standalone non-workspace callers have no cross-process workspace claim.
    """
    if os.name != "nt":
        raise RuntimeError("Windows native fence is platform-specific")
    binding = _current_local_inference_lease.get()
    if binding is None:
        return None
    with binding.gate:
        _verified_fds(binding)
        if binding.windows_fence is not None:
            raise RuntimeError("Windows native execution fence already active")
        os.lseek(binding.fd, 0, os.SEEK_SET)
        if os.read(binding.fd, 2) != b"\x00":
            raise RuntimeError("Windows native execution marker is not clean")
        nonce = object()
        binding.windows_fence = nonce
        os.lseek(binding.fd, 0, os.SEEK_SET)
        if os.write(binding.fd, b"\x01") != 1:
            raise RuntimeError("Windows native execution fence write incomplete")
        os.fsync(binding.fd)

    def complete() -> None:
        with binding.gate:
            _verified_fds(binding)
            if binding.windows_fence is not nonce:
                raise RuntimeError("Windows native execution fence is stale")
            os.lseek(binding.fd, 0, os.SEEK_SET)
            if os.read(binding.fd, 2) != b"\x01":
                raise RuntimeError("Windows native execution fence marker changed")
            os.lseek(binding.fd, 0, os.SEEK_SET)
            if os.write(binding.fd, b"\x00") != 1:
                raise RuntimeError("Windows native execution completion write incomplete")
            os.fsync(binding.fd)
            binding.windows_fence = None

    return complete


def gguf_child_pass_fds() -> tuple[int, ...]:
    """Observe bound FDs; actual Popen must use gguf_child_fd_scope()."""
    with gguf_child_fd_scope() as fds:
        return fds


__all__ = [
    "enter_local_lease", "leave_local_lease", "gguf_child_pass_fds",
    "gguf_child_fd_scope", "begin_windows_native_custody",
]
