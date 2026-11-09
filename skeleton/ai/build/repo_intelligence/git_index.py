"""Read-only, content-addressed Git index primitives for repository intelligence.

The scanner uses Git only to read index/ref metadata. Tracked working-tree content
is inspected by Python directly, so repository-controlled clean filters, external
diffs, fsmonitor hooks, and inherited ``GIT_*`` process overrides are never needed
to determine snapshot content. On platforms with secure ``dir_fd`` primitives,
every parent component is opened no-follow from the repository root; final
symlinks are hashed from link text and never followed. Gitlinks remain deliberately
opaque rather than recursing into nested repositories.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
from typing import Iterable, Iterator


_DEFAULT_MAX_BYTES = 20 * 1024 * 1024 * 1024
_GIT_CONFIG_ARGS = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.untrackedCache=false",
    "-c",
    "diff.external=",
)


class GitIndexError(RuntimeError):
    """Raised when a stable, safe repository snapshot cannot be proven."""


@dataclass(frozen=True, slots=True)
class TrackedFile:
    path: str
    mode: str
    index_blob: str
    effective_blob: str
    size: int
    working_tree: bool = False
    deleted: bool = False
    working_mode: str | None = None


@dataclass(frozen=True, slots=True)
class GitIndexSnapshot:
    head: str | None
    object_format: str
    source_digest: str
    tracked_files: int
    tracked_bytes: int
    files: tuple[TrackedFile, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": 1,
            "head": self.head,
            "object_format": self.object_format,
            "source_digest": self.source_digest,
            "tracked_files": self.tracked_files,
            "tracked_bytes": self.tracked_bytes,
            "files": [asdict(item) for item in self.files],
        }


@dataclass(frozen=True, slots=True)
class _EntryHandle:
    parent_fd: int | None
    name: str
    fallback_path: Path | None = None


class GitIndex:
    """Build a bounded, stable, read-only snapshot from one Git worktree."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_files: int = 200_000,
        max_total_bytes: int = _DEFAULT_MAX_BYTES,
        timeout_seconds: float = 20.0,
    ) -> None:
        if isinstance(max_files, bool) or not isinstance(max_files, int):
            raise TypeError("max_files must be an integer")
        if max_files <= 0:
            raise ValueError("max_files must be positive")
        if isinstance(max_total_bytes, bool) or not isinstance(max_total_bytes, int):
            raise TypeError("max_total_bytes must be an integer")
        if max_total_bytes <= 0:
            raise ValueError("max_total_bytes must be positive")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise TypeError("timeout_seconds must be numeric")
        if not 0 < float(timeout_seconds) <= 120:
            raise ValueError("timeout_seconds must be between 0 and 120")

        self.root = Path(root).resolve()
        self.max_files = max_files
        self.max_total_bytes = max_total_bytes
        self.timeout_seconds = float(timeout_seconds)
        if not self.root.is_dir():
            raise ValueError("root must be an existing directory")
        top = self._git(("rev-parse", "--show-toplevel")).strip()
        if Path(os.fsdecode(top)).resolve() != self.root:
            raise ValueError("root must be the Git worktree top level")

    @staticmethod
    def _safe_git_environment() -> dict[str, str]:
        # Inherited GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/config injection can
        # redirect a read to attacker-selected repository state. Strip the
        # entire GIT_* namespace and add only explicit safe controls.
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_PAGER": "cat",
                "LC_ALL": "C",
                "LANG": "C",
            }
        )
        return env

    def _git(self, args: Iterable[str], *, check: bool = True) -> bytes:
        args_tuple = tuple(args)
        command = ("git", *_GIT_CONFIG_ARGS, *args_tuple)
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                env=self._safe_git_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitIndexError(
                f"git command failed: {args_tuple[0] if args_tuple else 'unknown'}"
            ) from exc
        if check and completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()[:500]
            suffix = f": {detail}" if detail else ""
            raise GitIndexError(
                f"git command failed: {args_tuple[0] if args_tuple else 'unknown'}{suffix}"
            )
        return completed.stdout

    @staticmethod
    def _canonical_path(raw: bytes) -> str:
        path = os.fsdecode(raw)
        if not path or "\x00" in path or "\\" in path:
            raise GitIndexError("unsafe tracked path")
        pure = PurePosixPath(path)
        if (
            pure.is_absolute()
            or pure.as_posix() != path
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise GitIndexError("unsafe tracked path")
        return path

    def _index_entries(self, raw: bytes) -> list[tuple[str, str, str]]:
        entries: list[tuple[str, str, str]] = []
        unmerged = False
        for record in raw.split(b"\0"):
            if not record:
                continue
            try:
                meta, raw_path = record.split(b"\t", 1)
                mode_b, blob_b, stage_b = meta.split()
            except ValueError as exc:
                raise GitIndexError("malformed git index entry") from exc
            if stage_b != b"0":
                unmerged = True
                continue
            path = self._canonical_path(raw_path)
            try:
                mode = mode_b.decode("ascii")
                blob = blob_b.decode("ascii")
            except UnicodeDecodeError as exc:
                raise GitIndexError("malformed git index metadata") from exc
            if mode not in {"100644", "100755", "120000", "160000"}:
                raise GitIndexError("unsupported git index mode")
            entries.append((path, mode, blob))
            # Bound while parsing so a hostile index cannot materialize an
            # unbounded entry list before the advertised file-count limit.
            if len(entries) > self.max_files:
                raise GitIndexError("tracked file count exceeds configured limit")
        if unmerged:
            raise GitIndexError("unmerged index entries present")
        entries.sort(key=lambda item: os.fsencode(item[0]))
        return entries

    @staticmethod
    def _working_mode(st_mode: int) -> str:
        if stat.S_ISLNK(st_mode):
            return "120000"
        if stat.S_ISREG(st_mode):
            return "100755" if st_mode & stat.S_IXUSR else "100644"
        if stat.S_ISDIR(st_mode):
            return "040000"
        return "unknown"

    @staticmethod
    def _blob_digest(data: bytes, algorithm: str) -> str:
        digest = hashlib.new(algorithm)
        digest.update(f"blob {len(data)}\0".encode("ascii"))
        digest.update(data)
        return digest.hexdigest()

    @staticmethod
    def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
        return (
            left.st_dev == right.st_dev
            and left.st_ino == right.st_ino
            and left.st_mode == right.st_mode
            and left.st_size == right.st_size
            and left.st_mtime_ns == right.st_mtime_ns
            and left.st_ctime_ns == right.st_ctime_ns
        )

    @staticmethod
    def _supports_secure_dir_walk() -> bool:
        return (
            hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
            and os.open in os.supports_dir_fd
            and os.stat in os.supports_dir_fd
            and os.stat in os.supports_follow_symlinks
            and os.readlink in os.supports_dir_fd
        )

    def _fallback_entry(self, path_text: str) -> _EntryHandle:
        # Platforms without openat-style dir_fd support cannot make a nested
        # parent walk race-free. Fail closed for nested paths rather than risk
        # following an attacker-swapped parent symlink outside the worktree.
        parts = PurePosixPath(path_text).parts
        if len(parts) != 1:
            raise GitIndexError("secure nested path traversal is unavailable on this platform")
        return _EntryHandle(None, parts[0], self.root / parts[0])

    @contextmanager
    def _entry_handle(self, path_text: str) -> Iterator[_EntryHandle]:
        if not self._supports_secure_dir_walk():
            yield self._fallback_entry(path_text)
            return

        parts = PurePosixPath(path_text).parts
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC

        try:
            root_fd = os.open(self.root, flags)
        except OSError as exc:
            raise GitIndexError("unable to open repository root safely") from exc

        current_fd = root_fd
        try:
            for part in parts[:-1]:
                try:
                    next_fd = os.open(part, flags, dir_fd=current_fd)
                except FileNotFoundError:
                    # Missing parent means the tracked entry is deleted.
                    yield _EntryHandle(-1, parts[-1], None)
                    return
                except OSError as exc:
                    raise GitIndexError("unsafe tracked parent path") from exc
                if current_fd != root_fd:
                    os.close(current_fd)
                current_fd = next_fd
            yield _EntryHandle(current_fd, parts[-1], None)
        finally:
            if current_fd >= 0 and current_fd != root_fd:
                os.close(current_fd)
            os.close(root_fd)

    @staticmethod
    def _entry_lstat(handle: _EntryHandle) -> os.stat_result:
        if handle.parent_fd == -1:
            raise FileNotFoundError(handle.name)
        if handle.parent_fd is None:
            assert handle.fallback_path is not None
            return os.lstat(handle.fallback_path)
        return os.stat(handle.name, dir_fd=handle.parent_fd, follow_symlinks=False)

    @staticmethod
    def _entry_readlink(handle: _EntryHandle) -> str:
        if handle.parent_fd is None:
            assert handle.fallback_path is not None
            return os.readlink(handle.fallback_path)
        return os.readlink(handle.name, dir_fd=handle.parent_fd)

    @staticmethod
    def _entry_open(handle: _EntryHandle, flags: int) -> int:
        if handle.parent_fd is None:
            assert handle.fallback_path is not None
            return os.open(handle.fallback_path, flags)
        return os.open(handle.name, flags, dir_fd=handle.parent_fd)

    def _hash_regular_file(
        self,
        handle: _EntryHandle,
        algorithm: str,
        expected: os.stat_result,
        remaining_bytes: int,
    ) -> tuple[str, int, str]:
        if expected.st_size > remaining_bytes:
            raise GitIndexError("tracked byte count exceeds configured limit")

        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        try:
            fd = self._entry_open(handle, flags)
        except OSError as exc:
            raise GitIndexError("unable to open tracked file safely") from exc
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not self._same_file_state(expected, before):
                raise GitIndexError("tracked file changed type or identity during snapshot")

            digest = hashlib.new(algorithm)
            digest.update(f"blob {before.st_size}\0".encode("ascii"))
            total = 0
            while True:
                chunk = os.read(fd, min(1024 * 1024, remaining_bytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > remaining_bytes:
                    raise GitIndexError("tracked byte count exceeds configured limit")
                digest.update(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)

        if total != before.st_size or not self._same_file_state(before, after):
            raise GitIndexError("working tree changed during snapshot")
        return digest.hexdigest(), total, self._working_mode(before.st_mode)

    def _hash_symlink(
        self,
        handle: _EntryHandle,
        algorithm: str,
        before: os.stat_result,
        remaining_bytes: int,
    ) -> tuple[str, int, str]:
        try:
            target = self._entry_readlink(handle)
            after = self._entry_lstat(handle)
        except OSError as exc:
            raise GitIndexError("unable to read tracked symlink") from exc
        if not stat.S_ISLNK(after.st_mode) or not self._same_file_state(before, after):
            raise GitIndexError("tracked symlink changed during snapshot")
        data = os.fsencode(target)
        if len(data) > remaining_bytes:
            raise GitIndexError("tracked byte count exceeds configured limit")
        return self._blob_digest(data, algorithm), len(data), "120000"

    def _working_state(
        self,
        path_text: str,
        index_mode: str,
        index_blob: str,
        algorithm: str,
        remaining_bytes: int,
    ) -> tuple[str, int, bool, str | None]:
        with self._entry_handle(path_text) as handle:
            try:
                metadata = self._entry_lstat(handle)
            except FileNotFoundError:
                return "DELETED", 0, True, None
            except OSError as exc:
                raise GitIndexError("unable to stat tracked file") from exc

            if index_mode == "160000":
                # Never recurse into a nested repository. The superproject's
                # gitlink object is the authoritative bounded identity here.
                if not stat.S_ISDIR(metadata.st_mode):
                    raise GitIndexError("gitlink worktree entry has unexpected type")
                return index_blob, 0, False, "160000"

            if stat.S_ISLNK(metadata.st_mode):
                blob, size, mode = self._hash_symlink(
                    handle, algorithm, metadata, remaining_bytes
                )
                return blob, size, False, mode

            if stat.S_ISREG(metadata.st_mode):
                blob, size, mode = self._hash_regular_file(
                    handle, algorithm, metadata, remaining_bytes
                )
                return blob, size, False, mode

            raise GitIndexError("unsupported tracked file type in working tree")

    @staticmethod
    def _source_digest(files: Iterable[TrackedFile]) -> str:
        digest = hashlib.sha256()
        for item in files:
            effective_mode = item.working_mode or item.mode
            digest.update(os.fsencode(item.path))
            digest.update(b"\0")
            digest.update(item.mode.encode("ascii"))
            digest.update(b"\0")
            digest.update(effective_mode.encode("ascii"))
            digest.update(b"\0")
            digest.update(item.index_blob.encode("ascii"))
            digest.update(b"\0")
            digest.update(item.effective_blob.encode("ascii"))
            digest.update(b"\0")
            digest.update(str(item.size).encode("ascii"))
            digest.update(b"\0")
            digest.update(b"1" if item.working_tree else b"0")
            digest.update(b"1" if item.deleted else b"0")
            digest.update(b"\n")
        return digest.hexdigest()

    def _head(self) -> bytes:
        return self._git(("rev-parse", "--verify", "HEAD"), check=False).strip()

    def snapshot(self) -> GitIndexSnapshot:
        head_before = self._head()
        index_before = self._git(("ls-files", "-s", "-z"))
        entries = self._index_entries(index_before)

        object_format_raw = self._git(("rev-parse", "--show-object-format"))
        try:
            object_format = object_format_raw.decode("ascii", "strict").strip()
        except UnicodeDecodeError as exc:
            raise GitIndexError("invalid Git object format") from exc
        if object_format not in {"sha1", "sha256"}:
            raise GitIndexError("unsupported Git object format")

        rows: list[TrackedFile] = []
        total_bytes = 0
        for path, mode, index_blob in entries:
            effective, size, deleted, working_mode = self._working_state(
                path,
                mode,
                index_blob,
                object_format,
                self.max_total_bytes - total_bytes,
            )
            total_bytes += size
            mode_changed = working_mode is not None and working_mode != mode
            content_changed = effective != index_blob
            rows.append(
                TrackedFile(
                    path=path,
                    mode=mode,
                    index_blob=index_blob,
                    effective_blob=effective,
                    size=size,
                    working_tree=deleted or mode_changed or content_changed,
                    deleted=deleted,
                    working_mode=working_mode if mode_changed else None,
                )
            )

        # Re-read metadata after hashing. A moving ref or index can otherwise
        # produce a snapshot whose HEAD and index identities never coexisted.
        if self._git(("ls-files", "-s", "-z")) != index_before:
            raise GitIndexError("git index changed during snapshot")
        head_after = self._head()
        if head_after != head_before:
            raise GitIndexError("HEAD changed during snapshot")

        try:
            head = head_after.decode("ascii", "strict") if head_after else None
        except UnicodeDecodeError as exc:
            raise GitIndexError("invalid HEAD object id") from exc

        files = tuple(rows)
        return GitIndexSnapshot(
            head=head,
            object_format=object_format,
            source_digest=self._source_digest(files),
            tracked_files=len(files),
            tracked_bytes=total_bytes,
            files=files,
        )
