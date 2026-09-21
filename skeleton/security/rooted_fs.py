"""Capability-bounded filesystem operations for security-sensitive repository code.

The primitives in this module deliberately avoid "join a string and hope" file
access. A :class:`RootedFilesystem` owns one immutable root directory and every
operation:

* accepts only normalized workspace-relative paths;
* rejects symlinks in every existing path component;
* verifies opened descriptors still refer to the object that was inspected;
* applies explicit byte, file-count, and path-depth bounds;
* uses same-directory temporary files plus fsync + atomic replace for writes;
* never follows a symlink during deletion;
* emits content-addressed receipts suitable for audit/evidence planes.

The implementation is intentionally dependency-free. It is not a permission
system by itself: callers must still decide who is authorized to receive a
RootedFilesystem capability.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import hashlib
import io
import os
import secrets
from pathlib import Path
import shutil
import stat
from typing import BinaryIO, Iterable, Iterator, Mapping

from skeleton.shells.workspace_txn.pathing import (
    WorkspacePathError,
    normalize_relative_path,
)


# Capture platform capability once, before tests or callers wrap os functions.
# os.supports_dir_fd stores function objects; re-checking membership after a
# monkeypatch can incorrectly make a supported platform look unsupported.
_DIR_FD_CAPABILITIES_AVAILABLE = all(
    function in os.supports_dir_fd
    for function in (os.open, os.stat, os.mkdir)
)


class FilesystemBoundaryError(RuntimeError):
    """Base error for fail-closed rooted filesystem operations."""


class FilesystemPathError(FilesystemBoundaryError, ValueError):
    """Raised when a path cannot be proven to stay inside the root."""


class FilesystemQuotaError(FilesystemBoundaryError, ValueError):
    """Raised when a bounded filesystem operation would exceed policy."""


class FilesystemRaceError(FilesystemBoundaryError):
    """Raised when path metadata changes across a security boundary."""


@dataclass(frozen=True, slots=True)
class FilesystemLimits:
    """Resource limits enforced by a rooted filesystem capability."""

    max_read_bytes: int = 16 * 1024 * 1024
    max_write_bytes: int = 16 * 1024 * 1024
    max_stream_chunks: int = 65_536
    max_path_bytes: int = 1_024
    max_depth: int = 64
    max_directory_entries: int = 100_000

    def __post_init__(self) -> None:
        for name in (
            "max_read_bytes",
            "max_write_bytes",
            "max_stream_chunks",
            "max_path_bytes",
            "max_depth",
            "max_directory_entries",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class FileReceipt:
    """Immutable evidence for one successful file write."""

    path: str
    size: int
    sha256: str
    mode: int

    def __post_init__(self) -> None:
        if self.size < 0:
            raise ValueError("size must be non-negative")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise ValueError("sha256 must be lowercase hexadecimal")
        if not 0 <= self.mode <= 0o777:
            raise ValueError("mode outside permission range")


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    """Metadata snapshot captured without following symlinks."""

    path: str
    size: int
    mode: int
    mtime_ns: int
    inode: int
    device: int


def _safe_relative(value: str | os.PathLike[str], limits: FilesystemLimits) -> str:
    try:
        normalized = normalize_relative_path(value)
    except (WorkspacePathError, TypeError, ValueError) as exc:
        raise FilesystemPathError("invalid rooted filesystem path") from exc
    raw = os.fsencode(normalized)
    if len(raw) > limits.max_path_bytes:
        raise FilesystemQuotaError("path exceeds byte bound")
    depth = len(Path(normalized).parts)
    if depth > limits.max_depth:
        raise FilesystemQuotaError("path exceeds depth bound")
    return normalized


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_size)


def _regular_file(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode)


def _directory(info: os.stat_result) -> bool:
    return stat.S_ISDIR(info.st_mode)


def _bounded_mode(mode: int) -> int:
    if isinstance(mode, bool) or not isinstance(mode, int):
        raise ValueError("mode must be an integer")
    if mode < 0 or mode > 0o777:
        raise ValueError("mode outside permission range")
    # Security-owned artifacts are never made group/world writable by this API.
    if mode & 0o022:
        raise ValueError("group/world-writable mode is forbidden")
    return mode


class RootedFilesystem:
    """A filesystem capability permanently bound to one real directory."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        limits: FilesystemLimits | None = None,
    ) -> None:
        self.limits = limits or FilesystemLimits()
        candidate = Path(root).expanduser()
        try:
            root_lstat = candidate.lstat()
        except OSError as exc:
            raise FilesystemPathError("filesystem root is unavailable") from exc
        if stat.S_ISLNK(root_lstat.st_mode):
            raise FilesystemPathError("filesystem root must not be a symlink")
        if not stat.S_ISDIR(root_lstat.st_mode):
            raise FilesystemPathError("filesystem root must be a directory")
        try:
            resolved = candidate.resolve(strict=True)
            resolved_stat = resolved.stat()
        except OSError as exc:
            raise FilesystemPathError("filesystem root cannot be resolved") from exc
        if not stat.S_ISDIR(resolved_stat.st_mode):
            raise FilesystemPathError("filesystem root must resolve to a directory")
        self._root = resolved
        self._root_identity = (resolved_stat.st_dev, resolved_stat.st_ino)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def root_fingerprint(self) -> str:
        material = f"{self._root}\0{self._root_identity[0]}\0{self._root_identity[1]}".encode()
        return hashlib.sha256(material).hexdigest()

    def normalize(self, path: str | os.PathLike[str]) -> str:
        return _safe_relative(path, self.limits)

    def _assert_root_identity(self) -> None:
        try:
            info = self._root.stat()
        except OSError as exc:
            raise FilesystemRaceError("filesystem root became unavailable") from exc
        if (info.st_dev, info.st_ino) != self._root_identity:
            raise FilesystemRaceError("filesystem root identity changed")

    def _candidate(
        self,
        path: str | os.PathLike[str],
        *,
        allow_missing_final: bool = False,
        allow_missing_parents: bool = False,
    ) -> tuple[str, Path]:
        self._assert_root_identity()
        relative = self.normalize(path)
        parts = Path(relative).parts
        current = self._root

        for index, part in enumerate(parts):
            current = current / part
            final = index == len(parts) - 1
            try:
                info = current.lstat()
            except FileNotFoundError:
                if final and allow_missing_final:
                    break
                if allow_missing_parents:
                    break
                raise FilesystemPathError("path component does not exist") from None
            except OSError as exc:
                raise FilesystemPathError("path metadata is unavailable") from exc

            if stat.S_ISLNK(info.st_mode):
                raise FilesystemPathError("symlink path components are forbidden")
            if not final and not stat.S_ISDIR(info.st_mode):
                raise FilesystemPathError("non-directory path component")
        return relative, self._root.joinpath(*parts)

    def _ensure_parent(
        self,
        relative: str,
        *,
        create_parents: bool,
        parent_mode: int = 0o700,
    ) -> Path:
        parent_mode = _bounded_mode(parent_mode)
        parts = Path(relative).parts[:-1]
        current = self._root
        for part in parts:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                if not create_parents:
                    raise FilesystemPathError("parent directory does not exist") from None
                try:
                    current.mkdir(mode=parent_mode)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise FilesystemPathError("unable to create parent directory") from exc
                try:
                    info = current.lstat()
                except OSError as exc:
                    raise FilesystemRaceError("created parent cannot be inspected") from exc
            except OSError as exc:
                raise FilesystemPathError("parent metadata is unavailable") from exc
            if stat.S_ISLNK(info.st_mode):
                raise FilesystemPathError("parent path component is a symlink")
            if not stat.S_ISDIR(info.st_mode):
                raise FilesystemPathError("parent must be a real directory")
        return current

    @staticmethod
    def _directory_open_flags() -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        return flags

    def _open_directory_fd(
        self,
        parts: tuple[str, ...],
        *,
        create: bool,
        mode: int = 0o700,
    ) -> int:
        """Open a directory chain relative to the pinned root inode.

        Every component is traversed with descriptor-relative operations so a
        concurrent rename/symlink swap of a pathname cannot redirect later I/O
        outside the capability root.
        """
        mode = _bounded_mode(mode)
        if not _DIR_FD_CAPABILITIES_AVAILABLE:
            raise FilesystemBoundaryError(
                "descriptor-relative filesystem operations are unavailable"
            )
        self._assert_root_identity()
        flags = self._directory_open_flags()
        try:
            current_fd = os.open(self._root, flags)
        except OSError as exc:
            raise FilesystemRaceError("filesystem root cannot be opened safely") from exc
        try:
            root_info = os.fstat(current_fd)
            if (
                not stat.S_ISDIR(root_info.st_mode)
                or (root_info.st_dev, root_info.st_ino) != self._root_identity
            ):
                raise FilesystemRaceError("filesystem root identity changed")
            for part in parts:
                try:
                    next_fd = os.open(part, flags, dir_fd=current_fd)
                except FileNotFoundError:
                    if not create:
                        raise FilesystemPathError(
                            "parent directory does not exist"
                        ) from None
                    try:
                        os.mkdir(part, mode=mode, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    except OSError as exc:
                        raise FilesystemPathError(
                            "unable to create parent directory"
                        ) from exc
                    try:
                        next_fd = os.open(part, flags, dir_fd=current_fd)
                    except OSError as exc:
                        raise FilesystemRaceError(
                            "created parent cannot be opened safely"
                        ) from exc
                except OSError as exc:
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                        try:
                            entry = os.stat(
                                part,
                                dir_fd=current_fd,
                                follow_symlinks=False,
                            )
                        except OSError:
                            entry = None
                        if entry is not None and stat.S_ISLNK(entry.st_mode):
                            raise FilesystemPathError(
                                "parent path component is a symlink"
                            ) from exc
                    raise FilesystemPathError(
                        "parent directory cannot be opened safely"
                    ) from exc
                try:
                    info = os.fstat(next_fd)
                    if not stat.S_ISDIR(info.st_mode):
                        raise FilesystemPathError(
                            "parent must be a real directory"
                        )
                except BaseException:
                    os.close(next_fd)
                    raise
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except BaseException:
            os.close(current_fd)
            raise

    def _open_parent_fd(
        self,
        relative: str,
        *,
        create_parents: bool,
    ) -> tuple[int, str]:
        parts = Path(relative).parts
        if not parts:
            raise FilesystemPathError("file path is required")
        parent_fd = self._open_directory_fd(
            tuple(parts[:-1]),
            create=create_parents,
        )
        return parent_fd, parts[-1]

    def snapshot(self, path: str | os.PathLike[str]) -> FileSnapshot:
        relative, candidate = self._candidate(path)
        try:
            info = candidate.lstat()
        except OSError as exc:
            raise FilesystemPathError("unable to inspect file") from exc
        if stat.S_ISLNK(info.st_mode):
            raise FilesystemPathError("symlink files are forbidden")
        return FileSnapshot(
            path=relative,
            size=info.st_size,
            mode=stat.S_IMODE(info.st_mode),
            mtime_ns=info.st_mtime_ns,
            inode=info.st_ino,
            device=info.st_dev,
        )

    def exists(self, path: str | os.PathLike[str]) -> bool:
        try:
            self._candidate(path)
        except FilesystemPathError as exc:
            # Missing is the only non-exceptional false state; unsafe paths remain errors.
            if "does not exist" in str(exc):
                return False
            raise
        return True

    def read_bytes(
        self,
        path: str | os.PathLike[str],
        *,
        max_bytes: int | None = None,
    ) -> bytes:
        limit = self.limits.max_read_bytes if max_bytes is None else max_bytes
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("max_bytes must be a non-negative integer")
        limit = min(limit, self.limits.max_read_bytes)
        relative = self.normalize(path)
        parent_fd, name = self._open_parent_fd(
            relative,
            create_parents=False,
        )
        fd = -1
        try:
            try:
                before = os.stat(
                    name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise FilesystemPathError("file cannot be inspected") from exc
            if stat.S_ISLNK(before.st_mode):
                raise FilesystemPathError("read target must not be a symlink")
            if not _regular_file(before):
                raise FilesystemPathError("read target must be a regular file")
            if before.st_size > limit:
                raise FilesystemQuotaError("file exceeds read byte bound")

            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(
                    name,
                    flags,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                raise FilesystemPathError("file cannot be opened safely") from exc
            after = os.fstat(fd)
            if _stat_identity(before) != _stat_identity(after):
                raise FilesystemRaceError("file identity changed before read")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(fd, min(1024 * 1024, limit - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise FilesystemQuotaError("file exceeds read byte bound")
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            if fd >= 0:
                os.close(fd)
            os.close(parent_fd)

    def read_text(
        self,
        path: str | os.PathLike[str],
        *,
        encoding: str = "utf-8",
        max_bytes: int | None = None,
    ) -> str:
        data = self.read_bytes(path, max_bytes=max_bytes)
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeError) as exc:
            raise FilesystemBoundaryError("text decoding failed") from exc

    def _atomic_writer(
        self,
        relative: str,
        *,
        mode: int,
        create_parents: bool,
    ) -> tuple[int, int, str, str]:
        mode = _bounded_mode(mode)
        parent_fd, final_name = self._open_parent_fd(
            relative,
            create_parents=create_parents,
        )
        try:
            try:
                existing = os.stat(
                    final_name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                existing = None
            except OSError as exc:
                raise FilesystemPathError(
                    "write target cannot be inspected"
                ) from exc
            if existing is not None and (
                stat.S_ISLNK(existing.st_mode)
                or not stat.S_ISREG(existing.st_mode)
            ):
                raise FilesystemPathError(
                    "write target must be absent or a regular file"
                )

            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = -1
            temp_name = ""
            for _ in range(64):
                temp_name = (
                    f".{final_name}.{secrets.token_hex(12)}.tmp"
                )
                try:
                    fd = os.open(
                        temp_name,
                        flags,
                        mode,
                        dir_fd=parent_fd,
                    )
                    break
                except FileExistsError:
                    continue
                except OSError as exc:
                    raise FilesystemBoundaryError(
                        "unable to create atomic staging file"
                    ) from exc
            if fd < 0:
                raise FilesystemBoundaryError(
                    "atomic staging name retry budget exhausted"
                )
            try:
                os.fchmod(fd, mode)
            except BaseException:
                os.close(fd)
                try:
                    os.unlink(temp_name, dir_fd=parent_fd)
                except OSError:
                    pass
                raise
            return fd, parent_fd, temp_name, final_name
        except BaseException:
            os.close(parent_fd)
            raise

    @staticmethod
    def _commit_atomic_write(
        parent_fd: int,
        temp_name: str,
        final_name: str,
        *,
        fsync: bool,
    ) -> os.stat_result:
        try:
            os.replace(
                temp_name,
                final_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
        except (OSError, TypeError) as exc:
            raise FilesystemBoundaryError(
                "atomic replacement failed"
            ) from exc
        if fsync:
            os.fsync(parent_fd)
        try:
            info = os.stat(
                final_name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise FilesystemRaceError(
                "atomic replacement cannot be inspected"
            ) from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise FilesystemRaceError(
                "atomic replacement produced unsafe file type"
            )
        return info

    def write_bytes(
        self,
        path: str | os.PathLike[str],
        data: bytes | bytearray | memoryview,
        *,
        mode: int = 0o600,
        create_parents: bool = False,
        fsync: bool = True,
    ) -> FileReceipt:
        payload = bytes(data)
        if len(payload) > self.limits.max_write_bytes:
            raise FilesystemQuotaError("payload exceeds write byte bound")
        relative = self.normalize(path)
        fd, parent_fd, temp_name, final_name = self._atomic_writer(
            relative,
            mode=mode,
            create_parents=create_parents,
        )
        digest = hashlib.sha256()
        try:
            view = memoryview(payload)
            written = 0
            while written < len(view):
                count = os.write(fd, view[written:])
                if count <= 0:
                    raise FilesystemBoundaryError("short atomic file write")
                digest.update(view[written : written + count])
                written += count
            if fsync:
                os.fsync(fd)
            os.close(fd)
            fd = -1
            info = self._commit_atomic_write(
                parent_fd,
                temp_name,
                final_name,
                fsync=fsync,
            )
            os.close(parent_fd)
            parent_fd = -1
            return FileReceipt(
                path=relative,
                size=written,
                sha256=digest.hexdigest(),
                mode=stat.S_IMODE(info.st_mode),
            )
        except BaseException:
            if fd >= 0:
                os.close(fd)
            if parent_fd >= 0:
                try:
                    os.unlink(temp_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
                os.close(parent_fd)
            raise

    def write_text(
        self,
        path: str | os.PathLike[str],
        text: str,
        *,
        encoding: str = "utf-8",
        mode: int = 0o600,
        create_parents: bool = False,
        fsync: bool = True,
    ) -> FileReceipt:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        try:
            payload = text.encode(encoding)
        except (LookupError, UnicodeError) as exc:
            raise FilesystemBoundaryError("text encoding failed") from exc
        return self.write_bytes(
            path,
            payload,
            mode=mode,
            create_parents=create_parents,
            fsync=fsync,
        )

    def write_stream(
        self,
        path: str | os.PathLike[str],
        chunks: Iterable[bytes | bytearray | memoryview],
        *,
        expected_size: int | None = None,
        mode: int = 0o600,
        create_parents: bool = False,
        fsync: bool = True,
    ) -> FileReceipt:
        if expected_size is not None and (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
            or expected_size > self.limits.max_write_bytes
        ):
            raise FilesystemQuotaError("expected stream size outside write bound")
        relative = self.normalize(path)
        fd, parent_fd, temp_name, final_name = self._atomic_writer(
            relative,
            mode=mode,
            create_parents=create_parents,
        )
        digest = hashlib.sha256()
        total = 0
        chunk_count = 0
        try:
            for raw in chunks:
                chunk_count += 1
                if chunk_count > self.limits.max_stream_chunks:
                    raise FilesystemQuotaError("stream exceeds chunk-count bound")
                chunk = bytes(raw)
                total += len(chunk)
                if total > self.limits.max_write_bytes:
                    raise FilesystemQuotaError("stream exceeds write byte bound")
                view = memoryview(chunk)
                offset = 0
                while offset < len(view):
                    count = os.write(fd, view[offset:])
                    if count <= 0:
                        raise FilesystemBoundaryError("short atomic stream write")
                    digest.update(view[offset : offset + count])
                    offset += count
            if expected_size is not None and total != expected_size:
                raise FilesystemBoundaryError("stream size differs from declared size")
            if fsync:
                os.fsync(fd)
            os.close(fd)
            fd = -1
            info = self._commit_atomic_write(
                parent_fd,
                temp_name,
                final_name,
                fsync=fsync,
            )
            os.close(parent_fd)
            parent_fd = -1
            return FileReceipt(
                path=relative,
                size=total,
                sha256=digest.hexdigest(),
                mode=stat.S_IMODE(info.st_mode),
            )
        except BaseException:
            if fd >= 0:
                os.close(fd)
            if parent_fd >= 0:
                try:
                    os.unlink(temp_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
                os.close(parent_fd)
            raise

    def mkdir(
        self,
        path: str | os.PathLike[str],
        *,
        parents: bool = False,
        mode: int = 0o700,
    ) -> str:
        mode = _bounded_mode(mode)
        relative = self.normalize(path)
        parts = tuple(Path(relative).parts)
        if parents:
            directory_fd = self._open_directory_fd(
                parts,
                create=True,
                mode=mode,
            )
            os.close(directory_fd)
            return relative

        parent_fd = self._open_directory_fd(
            parts[:-1],
            create=False,
            mode=mode,
        )
        try:
            name = parts[-1]
            try:
                os.mkdir(name, mode=mode, dir_fd=parent_fd)
            except FileExistsError:
                pass
            except OSError as exc:
                raise FilesystemBoundaryError(
                    "directory creation failed"
                ) from exc
            flags = self._directory_open_flags()
            try:
                verify_fd = os.open(
                    name,
                    flags,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                raise FilesystemPathError(
                    "created directory cannot be opened safely"
                ) from exc
            try:
                info = os.fstat(verify_fd)
                if not stat.S_ISDIR(info.st_mode):
                    raise FilesystemPathError(
                        "directory path contains unsafe component"
                    )
            finally:
                os.close(verify_fd)
        finally:
            os.close(parent_fd)
        return relative

    def list_files(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        recursive: bool = False,
    ) -> tuple[str, ...]:
        if path is None:
            prefix = ""
            start_fd = self._open_directory_fd(
                (),
                create=False,
            )
        else:
            prefix = self.normalize(path)
            start_fd = self._open_directory_fd(
                tuple(Path(prefix).parts),
                create=False,
            )

        found: list[str] = []
        pending: list[tuple[str, int]] = [
            (prefix, start_fd)
        ]
        try:
            while pending:
                base_relative, directory_fd = pending.pop()
                try:
                    try:
                        entries = sorted(
                            os.scandir(directory_fd),
                            key=lambda item: item.name,
                        )
                    except OSError as exc:
                        raise FilesystemBoundaryError(
                            "directory enumeration failed"
                        ) from exc
                    if len(entries) > self.limits.max_directory_entries:
                        raise FilesystemQuotaError(
                            "directory entry bound exceeded"
                        )

                    child_dirs: list[tuple[str, int]] = []
                    try:
                        for entry in entries:
                            rel = (
                                f"{base_relative}/{entry.name}"
                                .strip("/")
                            )
                            rel = self.normalize(rel)
                            try:
                                info = os.stat(
                                    entry.name,
                                    dir_fd=directory_fd,
                                    follow_symlinks=False,
                                )
                            except OSError as exc:
                                raise FilesystemBoundaryError(
                                    "entry metadata failed"
                                ) from exc
                            if stat.S_ISLNK(info.st_mode):
                                raise FilesystemPathError(
                                    "symlink encountered during enumeration"
                                )
                            if stat.S_ISREG(info.st_mode):
                                found.append(rel)
                                if (
                                    len(found)
                                    > self.limits.max_directory_entries
                                ):
                                    raise FilesystemQuotaError(
                                        "file enumeration bound exceeded"
                                    )
                            elif stat.S_ISDIR(info.st_mode):
                                if recursive:
                                    flags = self._directory_open_flags()
                                    try:
                                        child_fd = os.open(
                                            entry.name,
                                            flags,
                                            dir_fd=directory_fd,
                                        )
                                    except OSError as exc:
                                        raise FilesystemRaceError(
                                            "directory changed during enumeration"
                                        ) from exc
                                    child_dirs.append(
                                        (rel, child_fd)
                                    )
                            else:
                                raise FilesystemPathError(
                                    "unsupported filesystem entry type"
                                )
                    except BaseException:
                        for _relative, descriptor in child_dirs:
                            try:
                                os.close(descriptor)
                            except OSError:
                                pass
                        raise
                    pending.extend(
                        reversed(child_dirs)
                    )
                finally:
                    os.close(directory_fd)
        except BaseException:
            for _relative, descriptor in pending:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise
        return tuple(found)

    def remove_file(self, path: str | os.PathLike[str]) -> None:
        relative = self.normalize(path)
        parent_fd, name = self._open_parent_fd(
            relative,
            create_parents=False,
        )
        try:
            try:
                before = os.stat(
                    name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise FilesystemPathError(
                    "remove target unavailable"
                ) from exc
            if (
                stat.S_ISLNK(before.st_mode)
                or not stat.S_ISREG(before.st_mode)
            ):
                raise FilesystemPathError(
                    "remove target must be a regular file"
                )
            try:
                os.unlink(
                    name,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                raise FilesystemBoundaryError(
                    "file removal failed"
                ) from exc
        finally:
            os.close(parent_fd)

    @contextmanager
    def temporary_directory(
        self,
        *,
        prefix: str = ".work-",
        mode: int = 0o700,
    ) -> Iterator["RootedFilesystem"]:
        mode = _bounded_mode(mode)
        if (
            not isinstance(prefix, str)
            or not prefix
            or "/" in prefix
            or "\\" in prefix
            or prefix in {".", ".."}
        ):
            raise FilesystemPathError(
                "invalid temporary-directory prefix"
            )
        if not getattr(
            shutil.rmtree,
            "avoids_symlink_attacks",
            False,
        ):
            raise FilesystemBoundaryError(
                "symlink-safe recursive cleanup is unavailable"
            )

        root_fd = self._open_directory_fd(
            (),
            create=False,
        )
        child_name = ""
        child_fd = -1
        try:
            for _ in range(64):
                candidate = (
                    f"{prefix}{secrets.token_hex(12)}"
                )
                try:
                    os.mkdir(
                        candidate,
                        mode=mode,
                        dir_fd=root_fd,
                    )
                    child_name = candidate
                    break
                except FileExistsError:
                    continue
                except OSError as exc:
                    raise FilesystemBoundaryError(
                        "temporary directory creation failed"
                    ) from exc
            if not child_name:
                raise FilesystemBoundaryError(
                    "temporary directory name retry budget exhausted"
                )

            flags = self._directory_open_flags()
            try:
                child_fd = os.open(
                    child_name,
                    flags,
                    dir_fd=root_fd,
                )
            except OSError as exc:
                raise FilesystemRaceError(
                    "temporary directory cannot be opened safely"
                ) from exc
            child_info = os.fstat(child_fd)
            if not stat.S_ISDIR(child_info.st_mode):
                raise FilesystemRaceError(
                    "temporary directory changed type"
                )

            child_path = self._root / child_name
            child = RootedFilesystem(
                child_path,
                limits=self.limits,
            )
            if child._root_identity != (
                child_info.st_dev,
                child_info.st_ino,
            ):
                raise FilesystemRaceError(
                    "temporary directory identity changed before handoff"
                )
            os.close(child_fd)
            child_fd = -1
            yield child
        finally:
            if child_fd >= 0:
                os.close(child_fd)
            if child_name:
                try:
                    shutil.rmtree(
                        child_name,
                        dir_fd=root_fd,
                    )
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise FilesystemBoundaryError(
                        "temporary directory cleanup failed"
                    ) from exc
            os.close(root_fd)


def receipts_digest(receipts: Iterable[FileReceipt]) -> str:
    """Return a deterministic digest over a set of file receipts."""

    material: list[str] = []
    for receipt in receipts:
        if not isinstance(receipt, FileReceipt):
            raise TypeError("receipts must contain FileReceipt values")
        material.append(
            f"{receipt.path}\0{receipt.size}\0{receipt.sha256}\0{receipt.mode:o}"
        )
    return hashlib.sha256("\n".join(sorted(material)).encode()).hexdigest()


__all__ = [
    "FileReceipt",
    "FileSnapshot",
    "FilesystemBoundaryError",
    "FilesystemLimits",
    "FilesystemPathError",
    "FilesystemQuotaError",
    "FilesystemRaceError",
    "RootedFilesystem",
    "receipts_digest",
]
