"""Kernel lease custody for locally spawned GGUF workers.

A POSIX flock belongs to an open file description. Native children inherit
that exact description, never an arbitrary recycled descriptor. Context
copies share revocation state and subprocess admission is serialized against
lease exit. Windows job-object qualification is separate.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
import os
import stat
from threading import Lock
from typing import Iterator


@dataclass
class _LeaseBinding:
    fd: int
    device: int
    inode: int
    owner_pid: int
    token: object | None = None
    active: bool = True
    gate: Lock = field(default_factory=Lock)


_current_local_inference_lease: ContextVar[_LeaseBinding | None] = ContextVar(
    "skeleton_local_gguf_lease", default=None,
)


def enter_local_lease(fd: int) -> Token[_LeaseBinding | None]:
    if type(fd) is not int or fd < 0:
        raise ValueError("invalid local inference lease descriptor")
    meta = os.fstat(fd)
    if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
            or (os.name == "posix" and (meta.st_uid != os.getuid() or meta.st_mode & 0o077))):
        raise ValueError("invalid local inference lease identity")
    binding = _LeaseBinding(fd, meta.st_dev, meta.st_ino, os.getpid())
    token = _current_local_inference_lease.set(binding)
    binding.token = token
    return token


def _require_owner_process(binding: _LeaseBinding) -> None:
    try:
        pid = os.getpid()
    except Exception as exc:
        raise RuntimeError("local inference process identity unavailable") from exc
    if type(pid) is not int or pid != binding.owner_pid:
        raise RuntimeError("local inference process identity changed")


def leave_local_lease(token: Token[_LeaseBinding | None]) -> None:
    binding = _current_local_inference_lease.get()
    if binding is None:
        raise RuntimeError("local inference lease context missing")
    _require_owner_process(binding)
    if binding.token is not token:
        raise RuntimeError("local inference lease token does not own current binding")
    with binding.gate:
        # A copied context cannot reset the original token; do not revoke
        # valid parent authority unless context reset actually succeeds.
        _current_local_inference_lease.reset(token)
        binding.active = False


def _verified_fds(binding: _LeaseBinding) -> tuple[int, ...]:
    _require_owner_process(binding)
    if not binding.active:
        raise RuntimeError("local inference lease context revoked")
    meta = os.fstat(binding.fd)
    if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
            or (meta.st_dev, meta.st_ino) != (binding.device, binding.inode)
            or (os.name == "posix" and (meta.st_uid != os.getuid() or meta.st_mode & 0o077))):
        raise RuntimeError("local inference lease descriptor identity changed")
    return (binding.fd,)


@contextmanager
def gguf_child_fd_scope() -> Iterator[tuple[int, ...]]:
    """Hold admission across Popen, preventing revocation-before-inheritance."""
    binding = _current_local_inference_lease.get()
    if binding is None:
        yield ()
        return
    _require_owner_process(binding)
    with binding.gate:
        if not binding.active:
            raise RuntimeError("local inference lease context revoked")
        yield _verified_fds(binding) if os.name == "posix" else ()


def gguf_child_pass_fds() -> tuple[int, ...]:
    """Observe bound FDs; actual Popen must use gguf_child_fd_scope()."""
    with gguf_child_fd_scope() as fds:
        return fds


__all__ = ["enter_local_lease", "leave_local_lease", "gguf_child_pass_fds", "gguf_child_fd_scope"]
