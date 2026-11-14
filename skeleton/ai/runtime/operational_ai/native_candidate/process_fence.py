"""POSIX model-scoped training process lease, never a distributed consensus claim.

Locking excludes concurrent trainers on the same trusted local state root.
The live serving model is still protected by immutable cloning.
"""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import time

from .strict import sha, number
from .errors import deny


@contextmanager
def model_training_fence(
    state_directory: Path, model_sha256: str, *,
    deadline_ms: int = 20000,
):
    from ..model.gguf.file_guard import open_trusted_root
    sha(model_sha256, "lock-model")
    number(deadline_ms, "lock-deadline", 1, 60000)
    if type(state_directory) is not Path or not state_directory.is_absolute():
        deny("lock-root")
    root = open_trusted_root(state_directory)
    try:
        info = os.fstat(root)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
            deny("lock-private-root")
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
