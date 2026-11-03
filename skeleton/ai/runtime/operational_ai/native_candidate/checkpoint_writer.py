"""Strict owner-private, content-addressed candidate publication.

Use Linux/POSIX descriptor ancestry and O_EXCL. No overwrites, symlinks,
hardlinks, unbounded content, raw temporary path races or serving activation.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from .errors import deny
from .strict import bytes_sha, number
from .trainer import CandidateTrainingResult


def _root(directory: Path) -> int:
    from ..model.gguf.file_guard import open_trusted_root
    if type(directory) is not Path or not directory.is_absolute():
        deny("candidate-root")
    try:
        fd = open_trusted_root(directory)
    except (OSError, ValueError):
        deny("candidate-parent-unsafe")
    mode = os.fstat(fd)
    if not stat.S_ISDIR(mode.st_mode) or mode.st_mode & 0o077 or mode.st_uid != os.geteuid():
        os.close(fd)
        deny("candidate-root-private")
    return fd


def _write_new(fd: int, name: str, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    child = os.open(name, flags, 0o600, dir_fd=fd)
    try:
        with os.fdopen(child, "wb", closefd=True) as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        try:
            os.unlink(name, dir_fd=fd)
        except OSError:
            pass
        raise


def publish(result: CandidateTrainingResult, directory: Path) -> dict:
    if type(result) is not CandidateTrainingResult:
        deny("candidate-result-type")
    raw = result.checkpoint_json
    if type(raw) is not bytes or not 1 <= len(raw) <= 256000000:
        deny("candidate-output-size")
    digest = bytes_sha(raw)
    leaf = digest + ".native.json"
    directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    root_fd = _root(directory)
    try:
        # Do not silently accept a different artifact at an existing name.
        try:
            st = os.stat(leaf, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            st = None
        if st is not None:
            deny("candidate-already-exists-review-before-retry")
        _write_new(root_fd, leaf, raw)
        os.fsync(root_fd)
        return {
            "schema": "skeleton.native-candidate.publication.v1",
            "path": str(directory / leaf),
            "checkpoint_sha256": digest, "bytes": len(raw),
            "candidate_digest": result.candidate.digest,
            "candidate_model_digest": result.candidate.weights_digest,
            "kind": "candidate-only",
            "serving_activation": False,
            "release_certified": False,
        }
    finally:
        os.close(root_fd)
