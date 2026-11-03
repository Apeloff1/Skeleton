"""Descriptor-anchored private report publication; no-clobber and durable fsync.

The model weight shard custody root opener is reused, not reimplemented.
No parent-directory symlink or world-writable intermediary is accepted.
"""
from __future__ import annotations
import os
from pathlib import Path
import stat
from .canonical import encode, sha256, identity
from .errors import deny
from .privacy import inspect_public_fields
from .report import QualificationReport


def save_new_private(report: QualificationReport, directory: Path, name: str) -> dict:
    if type(report) is not QualificationReport:
        deny("write-report-type")
    if type(directory) is not Path or not directory.is_absolute():
        deny("write-root")
    identity(name, "report-name")
    record = report.record()
    privacy = inspect_public_fields(record)
    if not privacy["publishable"]:
        deny("write-private-content")
    data = encode(record)
    if len(data) > 8 * 1024 * 1024:
        deny("write-report-size")
    directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    from skeleton.ai.runtime.operational_ai.model.gguf.file_guard import open_trusted_root
    try:
        root_fd = open_trusted_root(directory)
    except (OSError, ValueError) as exc:
        raise RuntimeError("unsafe report parent directory") from exc
    try:
        st = os.fstat(root_fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.geteuid():
            deny("write-permission")
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
