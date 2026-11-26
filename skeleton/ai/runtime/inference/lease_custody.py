"""Descriptor identity and lifetime fences for local GGUF child leases.

A POSIX flock belongs to the shared open file description, not the numeric
descriptor. The trusted caller owns acquisition. A copied asyncio context
must not continue to authorize inheritance after its owning scope leaves.
These checks cannot prove that a caller actually acquired a flock, or that
an arbitrary native executable retains inherited descriptors.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
import os
import stat
import threading


def _identity(fd: int) -> tuple[int, int, int]:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("inference lease descriptor must name a regular file")
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


@dataclass(slots=True)
class _LeaseBinding:
    fd: int
    identity: tuple[int, int, int]
    active: bool = True
    token: Token | None = None


# Shared binding state deliberately survives ContextVar copying into an
# asyncio.to_thread worker. Revocation invalidates those copies as well.
_current_local_inference_lease_fd: ContextVar[_LeaseBinding | None] = ContextVar(
    "skeleton_local_gguf_lease_fd", default=None,
)
_lock = threading.RLock()


def enter_local_lease(fd: int) -> Token[_LeaseBinding | None]:
    if type(fd) is not int or fd < 0:
        raise ValueError("invalid local inference lease descriptor")
    with _lock:
        binding = _LeaseBinding(fd, _identity(fd))
        token = _current_local_inference_lease_fd.set(binding)
        binding.token = token
        return token


def leave_local_lease(token: Token[_LeaseBinding | None]) -> None:
    with _lock:
        binding = _current_local_inference_lease_fd.get()
        if binding is None or binding.token is not token or not binding.active:
            raise ValueError("inference lease scopes must leave in owning LIFO order")
        # Reset first: an invalid/foreign/reused token cannot revoke the
        # currently valid binding. Correct callers leave in LIFO order.
        _current_local_inference_lease_fd.reset(token)
        binding.active = False
        binding.token = None


def gguf_child_pass_fds() -> tuple[int, ...]:
    """Return only a live descriptor whose observed identity still matches."""
    if os.name != "posix":
        return ()
    with _lock:
        binding = _current_local_inference_lease_fd.get()
        if binding is None:
            return ()
        if not binding.active:
            raise ValueError("local inference lease scope has ended")
        if _identity(binding.fd) != binding.identity:
            raise ValueError("local inference lease descriptor identity changed")
        return (binding.fd,)


__all__ = ["enter_local_lease", "leave_local_lease", "gguf_child_pass_fds", "gguf_child_fd_scope"]
