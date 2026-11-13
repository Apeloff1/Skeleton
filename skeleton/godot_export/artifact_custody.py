"""Fail-closed custody of a Godot desktop export.

A successful Godot process exit is not evidence of a usable artifact. This
module verifies that an export produced a new, bounded, regular executable
with a recognizable platform header and records its content digest.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .runner import GodotRunner, RunResult

MAX_EXPORT_BYTES = 2 * 1024 * 1024 * 1024
CHUNK = 1024 * 1024


class ExportCustodyError(ValueError):
    """Export cannot be admitted as an independently inspectable artifact."""


@dataclass(frozen=True)
class ExportEvidence:
    path: str
    platform: str
    size: int
    sha256: str
    godot_exit_code: int


def _regular_file(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ExportCustodyError("artifact-missing") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ExportCustodyError("artifact-not-single-regular-file")
    if not 0 < info.st_size <= MAX_EXPORT_BYTES:
        raise ExportCustodyError("artifact-size-invalid")
    return info


def inspect_export(path: Path, platform: str, *, root: Path, result: RunResult) -> ExportEvidence:
    """Validate an actual binary; never mistake a successful process for proof.

    The output must be under an existing trusted export directory. A caller
    must control that directory; untrusted writers must not share it.
    """
    if platform not in {"windows", "linux"}:
        raise ExportCustodyError("unsupported-platform")
    if not result.ok:
        raise ExportCustodyError("godot-export-failed")
    if path.is_symlink() or root.is_symlink():
        raise ExportCustodyError("export-symlink")
    try:
        canonical_root = root.resolve(strict=True)
        canonical_path = path.resolve(strict=True)
        canonical_path.relative_to(canonical_root)
    except (OSError, ValueError) as exc:
        raise ExportCustodyError("artifact-outside-export-root") from exc
    before = _regular_file(canonical_path)
    digest = hashlib.sha256()
    try:
        with canonical_path.open("rb") as stream:
            signature = stream.read(4)
            if platform == "windows" and signature[:2] != b"MZ":
                raise ExportCustodyError("invalid-pe-signature")
            if platform == "linux" and signature != b"\x7fELF":
                raise ExportCustodyError("invalid-elf-signature")
            digest.update(signature)
            total = len(signature)
            while True:
                block = stream.read(CHUNK)
                if not block:
                    break
                total += len(block)
                if total > MAX_EXPORT_BYTES:
                    raise ExportCustodyError("artifact-too-large")
                digest.update(block)
    except OSError as exc:
        raise ExportCustodyError("artifact-read-failed") from exc
    after = _regular_file(canonical_path)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ) or total != after.st_size:
        raise ExportCustodyError("artifact-changed-during-verification")
    return ExportEvidence(str(canonical_path), platform, total, digest.hexdigest(), result.code)


def export_and_inspect(
    runner: GodotRunner, project: Path, preset: str, output: Path, platform: str,
    *, timeout: int = 600,
) -> ExportEvidence:
    """Run the real configured Godot exporter and inspect its emitted binary.

    Requires a dedicated export directory. Never overwrites an existing
    artifact, including symlinks and broken links.
    """
    if not preset or not isinstance(preset, str):
        raise ExportCustodyError("preset-required")
    if output.exists() or output.is_symlink():
        raise ExportCustodyError("output-already-exists")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ExportCustodyError("unsafe-output-directory")
    result = runner.export(project, preset, str(output), timeout=timeout)
    return inspect_export(output, platform, root=output.parent, result=result)
