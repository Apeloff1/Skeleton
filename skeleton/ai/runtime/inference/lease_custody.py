"""Process-death protection for a locally spawned GGUF inference worker.

A POSIX flock is attached to an open file description. Passing that existing
descriptor into a verified native child keeps the SAME kernel lease alive if
the Python supervisor is abruptly killed before it can terminate the child.

This does not authorize subprocess creation and carries no secrets. A separate
OS-backed local inference lease owns the descriptor and lifetime; ordinary
Python tasks have no inheritable descriptor. Windows requires an independent
job-object kill-on-close qualification instead of assuming POSIX semantics.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
import os

# ContextVar follows asyncio task creation and asyncio.to_thread worker
# delegation, unlike a thread-local variable. Its value is only an existing,
# nonsecret kernel descriptor, never a model path or authentication credential.
_current_local_inference_lease_fd: ContextVar[int | None] = ContextVar(
    "skeleton_local_gguf_lease_fd", default=None,
)


def enter_local_lease(fd: int) -> Token[int | None]:
    if type(fd) is not int or fd < 0:
        raise ValueError("invalid local inference lease descriptor")
    os.fstat(fd)
    return _current_local_inference_lease_fd.set(fd)


def leave_local_lease(token: Token[int | None]) -> None:
    _current_local_inference_lease_fd.reset(token)


def gguf_child_pass_fds() -> tuple[int, ...]:
    """Return only the *currently held* lease FD for a POSIX Popen.

    Popen must use `pass_fds=...` with `close_fds=True`. If the parent dies
    while the child is executing, no explicit LOCK_UN occurs: the inherited
    file description retains the lock until the child exits. Normal completion
    already waits for the native child to terminate before releasing the
    parent lease.
    """
    if os.name != "posix":
        return ()
    fd = _current_local_inference_lease_fd.get()
    if fd is None:
        return ()
    # Refuse to continue with a stale/reused descriptor. A missing FD is a
    # contract failure, not permission to spawn an unlocked GGUF executor.
    os.fstat(fd)
    return (fd,)


__all__ = ["enter_local_lease", "leave_local_lease", "gguf_child_pass_fds"]
