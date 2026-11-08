"""Source-bound inspection and no-clobber publication of real Godot exports.

This is artifact *custody*, not proof that an executable launches, runs a game,
is signed, or came from a trusted Godot binary. A dedicated trusted output
directory and a separately verified Godot installation remain prerequisites.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
from dataclasses import dataclass

from .runner import GodotRunner, RunResult

MAX_EXPORT_BYTES = 2 * 1024 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
MAX_PE_HEADER_OFFSET = 4 * 1024 * 1024


class ExportCustodyError(ValueError):
    """No release or executable admissibility follows from a failed check."""


@dataclass(frozen=True, slots=True)
class ExportEvidence:
    path: str
    platform: str
    size: int
    sha256: str
    godot_exit_code: int


def _root_stat(root: Path) -> os.stat_result:
    try:
        info = root.lstat()
    except OSError as exc:
        raise ExportCustodyError("export-root-unavailable") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ExportCustodyError("export-root-not-a-directory")
    return info


def _stat_regular(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ExportCustodyError("artifact-not-single-regular-file")
    if not 0 < info.st_size <= MAX_EXPORT_BYTES:
        raise ExportCustodyError("artifact-size-invalid")


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink)


def _validate_image(stream, platform: str, size: int) -> None:
    if platform == "windows":
        if size < 0x84:
            raise ExportCustodyError("invalid-pe-signature")
        start = stream.read(64)
        if start[:2] != b"MZ":
            raise ExportCustodyError("invalid-pe-signature")
        offset = int.from_bytes(start[0x3C:0x40], "little")
        if offset < 0x40 or offset > MAX_PE_HEADER_OFFSET or offset + 4 > size:
            raise ExportCustodyError("invalid-pe-header-offset")
        stream.seek(offset)
        if stream.read(4) != b"PE\x00\x00":
            raise ExportCustodyError("invalid-pe-signature")
    elif platform == "linux":
        start = stream.read(16)
        if (len(start) != 16 or start[:4] != b"\x7fELF" or
                start[4] not in (1, 2) or start[5] not in (1, 2) or
                start[6] != 1):
            raise ExportCustodyError("invalid-elf-signature")
    else:
        raise ExportCustodyError("unsupported-platform")
    stream.seek(0)


def inspect_export(
    path: Path, platform: str, *, root: Path, result: RunResult
) -> ExportEvidence:
    """Inspect a direct child of a trusted directory using an opened file.

    POSIX uses a pinned directory descriptor and O_NOFOLLOW. On Windows, where
    dir_fd is unavailable, the caller-owned directory and file identity are
    checked before and after read. Untrusted concurrent writers are forbidden.
    """
    if platform not in ("windows", "linux"):
        raise ExportCustodyError("unsupported-platform")
    if not isinstance(result, RunResult) or not result.ok:
        raise ExportCustodyError("godot-export-failed")
    root, path = Path(root), Path(path)
    if path.parent != root or path.name in ("", ".", ".."):
        raise ExportCustodyError("artifact-outside-export-root")

    root_before = _root_stat(root)
    directory_fd = None
    fd = None
    try:
        posix_anchor = (hasattr(os, "O_NOFOLLOW") and
                        hasattr(os, "O_DIRECTORY") and
                        os.open in os.supports_dir_fd and
                        os.stat in os.supports_dir_fd)
        if posix_anchor:
            directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            root_opened = os.fstat(directory_fd)
            if ((root_opened.st_dev, root_opened.st_ino) !=
                    (root_before.st_dev, root_before.st_ino)):
                raise ExportCustodyError("export-root-replaced")
            before = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
            _stat_regular(before)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW |
                         getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
        else:
            before = path.lstat()
            _stat_regular(before)
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        opened = os.fstat(fd)
        _stat_regular(opened)
        if _file_identity(opened) != _file_identity(before):
            raise ExportCustodyError("artifact-replaced-before-verification")
        digest = hashlib.sha256()
        with os.fdopen(os.dup(fd), "rb") as stream:
            _validate_image(stream, platform, opened.st_size)
            size = 0
            while block := stream.read(CHUNK_BYTES):
                size += len(block)
                if size > MAX_EXPORT_BYTES:
                    raise ExportCustodyError("artifact-size-invalid")
                digest.update(block)
        after_fd = os.fstat(fd)
        if directory_fd is not None:
            after_path = os.stat(path.name, dir_fd=directory_fd,
                                 follow_symlinks=False)
        else:
            after_path = path.lstat()
        root_after = _root_stat(root)
        if ((root_after.st_dev, root_after.st_ino) !=
                (root_before.st_dev, root_before.st_ino) or
                _file_identity(opened) != _file_identity(after_fd) or
                _file_identity(opened) != _file_identity(after_path) or
                size != opened.st_size):
            raise ExportCustodyError("artifact-changed-during-verification")
        return ExportEvidence(str(path), platform, size, digest.hexdigest(), result.code)
    except (OSError, OverflowError) as exc:
        raise ExportCustodyError("artifact-io-failed") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)


def export_and_inspect(
    runner: GodotRunner, project: Path, preset: str, output: Path,
    platform: str, *, timeout: int = 600
) -> ExportEvidence:
    """Export into a private sibling directory, then atomically link into place.

    An existing destination is never modified. Atomic hardlink publication
    keeps consumers from observing a partially written executable. If the
    underlying filesystem cannot provide this primitive, fail closed.
    """
    if platform not in ("windows", "linux"):
        raise ExportCustodyError("unsupported-platform")
    if (not isinstance(preset, str) or not preset or
            len(preset) > 128 or preset != preset.strip() or
            any(ord(c) < 32 for c in preset)):
        raise ExportCustodyError("preset-invalid")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 0 < timeout <= 3600:
        raise ExportCustodyError("timeout-invalid")
    project, output = Path(project), Path(output)
    if not project.is_dir() or project.is_symlink():
        raise ExportCustodyError("project-root-invalid")
    output_root = output.parent
    _root_stat(output_root)
    if output.name in ("", ".", "..") or output.exists() or output.is_symlink():
        raise ExportCustodyError("output-already-exists")
    staged_root = Path(tempfile.mkdtemp(prefix=".godot-export-", dir=output_root))
    try:
        staged = staged_root / output.name
        try:
            run = runner.export(project, preset, str(staged), timeout=timeout)
        except (OSError, ValueError) as exc:
            raise ExportCustodyError("godot-export-failed") from exc
        inspect_export(staged, platform, root=staged_root, result=run)
        try:
            os.link(staged, output, follow_symlinks=False)
        except (FileExistsError, OSError) as exc:
            raise ExportCustodyError("atomic-publication-unavailable-or-colliding") from exc
    finally:
        shutil.rmtree(staged_root)
    # The private staging hardlink has now gone away; final link count is one.
    # A failed final check never emits evidence and never claims release.
    return inspect_export(output, platform, root=output_root, result=run)
