"""Descriptor-anchored private report publication; no-clobber and durable fsync.

The model weight shard custody root opener is reused, not reimplemented.
No parent-directory symlink or world-writable intermediary is accepted.
"""
from __future__ import annotations
import os
from pathlib import Path
from .canonical import encode, sha256, identity
from .errors import deny
from .privacy import inspect_public_fields
from .report import QualificationReport
from ..recovered_path_custody import require_absolute_directory, open_private_directory


def save_new_private(report: QualificationReport, directory: Path, name: str) -> dict:
    if type(report) is not QualificationReport:
        deny("write-report-type")
    try:
        require_absolute_directory(directory)
    except ValueError:
        deny("write-root")
    identity(name, "report-name")
    record = report.record()
    privacy = inspect_public_fields(record)
    if not privacy["publishable"]:
        deny("write-private-content")
    data = encode(record)
    if len(data) > 8 * 1024 * 1024:
        deny("write-report-size")
    try:
        root_fd = open_private_directory(directory, create=True)
    except (OSError, ValueError) as exc:
        raise RuntimeError("unsafe report parent directory") from exc
    try:
        leaf = name + ".json"
        fd = os.open(
            leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=root_fd,
        )
        try:
            with os.fdopen(fd, "wb", closefd=True) as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
        except BaseException:
            try:
                os.unlink(leaf, dir_fd=root_fd)
            except OSError:
                pass
            raise
        os.fsync(root_fd)
        return {"path": str(directory / leaf), "sha256": sha256(data), "bytes": len(data)}
    finally:
        os.close(root_fd)
