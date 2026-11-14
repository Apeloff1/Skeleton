"""POSIX model-scoped training process lease, never a distributed consensus claim.

Locking excludes concurrent trainers on the same trusted local state root.
The live serving model is still protected by immutable cloning.
"""
from __future__ import annotations
from contextlib import contextmanager
try:
    import fcntl
except ImportError:  # Native process custody is POSIX-only.
    fcntl = None
import os
from pathlib import Path
import stat
import time

from .strict import sha, number
from .errors import deny
from ..recovered_path_custody import open_private_directory


@contextmanager
def model_training_fence(
    state_directory: Path, model_sha256: str, *,
    deadline_ms: int = 20000,
):
    sha(model_sha256, "lock-model")
    number(deadline_ms, "lock-deadline", 1, 60000)
    if fcntl is None:
        deny("training-lock-posix-required")
    try:
        root = open_private_directory(state_directory, create=False)
    except (OSError, ValueError):
        deny("lock-private-root")
    try:
        leaf = "model_training_" + model_sha256[:32] + ".lock"
        fd = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=root)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_nlink != 1:
                deny("lock-inode")
            if st.st_mode & 0o077:
                deny("lock-permissions")
            end = time.monotonic_ns() + deadline_ms * 1000000
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic_ns() >= end:
                        deny("training-lock-timeout")
                    time.sleep(0.025)
            try:
                yield {"model_sha256": model_sha256,
                       "state": "local-process-exclusive",
                       "distributed_lease": False}
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    finally:
        os.close(root)
