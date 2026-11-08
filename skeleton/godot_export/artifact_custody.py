"""Fail-closed, independently inspectable Godot export artifact custody.

A zero process exit is not evidence that a standalone game was produced.
This module validates the actual artifact after the canonical GodotRunner
has invoked the installed engine. It does not certify real playability.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .runner import GodotRunner, RunResult


@dataclass(frozen=True)
class ExportEvidence:
    result: RunResult
    artifact: str | None
    sha256: str | None
    size: int
    failure: str | None

    @property
    def verified(self) -> bool:
        return self.failure is None and self.sha256 is not None


def export_with_evidence(
    runner: GodotRunner,
    project: Path,
    preset: str,
    artifact: Path,
    *,
    mode: str = "release",
    timeout: int = 600,
    max_bytes: int = 2_000_000_000,
) -> ExportEvidence:
    """Run Godot then hash a regular newly created output without following symlinks.

    The destination must be inside the project, absent before the export,
    and must remain the same inode throughout hashing. A failed export never
    returns success just because a stale artifact was already on disk.
    """
    absent = RunResult(127, "export not invoked")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        return ExportEvidence(absent, None, None, 0, "invalid_size_budget")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
        return ExportEvidence(absent, None, None, 0, "invalid_timeout")
    if not preset or not isinstance(preset, str) or "\x00" in preset:
        return ExportEvidence(absent, None, None, 0, "invalid_preset")
    try:
        root = project.resolve(strict=True)
        if not root.is_dir() or root.is_symlink():
            raise ValueError("invalid project")
        target = artifact.absolute()
        relative = target.relative_to(root)
        if not relative.parts or any(part in (".", "..") for part in relative.parts):
            raise ValueError("unsafe artifact path")
        parent = target.parent.resolve(strict=True)
        parent.relative_to(root)
        if target.exists() or target.is_symlink():
            return ExportEvidence(absent, None, None, 0, "artifact_already_exists")
    except (OSError, ValueError):
        return ExportEvidence(absent, None, None, 0, "unsafe_artifact_path")
    try:
        result = runner.export(root, preset, str(target), mode=mode, timeout=timeout)
    except (OSError, ValueError) as exc:
        return ExportEvidence(absent, None, None, 0, "engine_invocation_failed:" + type(exc).__name__)
    if not result.ok:
        return ExportEvidence(result, None, None, 0, "engine_export_failed")
    fd = None
    try:
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 1 or before.st_size > max_bytes:
            return ExportEvidence(result, None, None, 0, "invalid_artifact")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                return ExportEvidence(result, None, None, 0, "artifact_exceeds_budget")
            digest.update(chunk)
        after = os.fstat(fd)
        path_stat = os.lstat(target)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or (after.st_dev, after.st_ino) != (path_stat.st_dev, path_stat.st_ino) or total != after.st_size:
            return ExportEvidence(result, None, None, 0, "artifact_changed_during_read")
        if not stat.S_ISREG(path_stat.st_mode):
            return ExportEvidence(result, None, None, 0, "artifact_not_regular")
        return ExportEvidence(result, str(target), digest.hexdigest(), total, None)
    except OSError:
        return ExportEvidence(result, None, None, 0, "artifact_unreadable")
    finally:
        if fd is not None:
            os.close(fd)
