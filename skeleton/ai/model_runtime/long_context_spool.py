"""Immutable, crash-recoverable token context custody for offline native inference.

The spool stores canonical token sequences and append-only progress checkpoints.
It does not claim to persist model KV tensors or to authenticate an untrusted
publisher. Callers retain the returned checkpoint digest as their resume token.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
from time import monotonic_ns, sleep
from typing import Any

from .flgb_model_runtime import TokenSequence
from .tokenization import (
    MAX_SERIALIZED_SEQUENCE_BYTES,
    TokenWindow,
    TokenizerContractError,
    deserialize_token_sequence,
    serialize_token_sequence,
)

_SCHEMA = "skeleton.ai.long-context-spool.v1"
_CHUNK = 1024 * 1024
MAX_WINDOW_TOKENS = 65_536
DEFAULT_WINDOW_TOKENS = 4_096
_PUBLISH_LOCK_WAIT_NS = 2_000_000_000
_RECOVERY_MAX_ENTRIES = 64
_RECOVERY_MAX_SCAN = 4096
_RECOVERY_MAX_BYTES = 128 * 1024 * 1024
_DEFAULT_SPOOL_QUOTA_BYTES = 4 * 1024 * 1024 * 1024
_MAX_SPOOL_QUOTA_BYTES = 1024 * 1024 * 1024 * 1024
_QUOTA_MAX_ENTRIES = 65_536



class LongContextSpoolError(TokenizerContractError):
    """A source, custody, disk-budget, or checkpoint contract failed."""


def _require_private_spool_file(fd: int) -> None:
    """Reject files that other local principals can read or replace."""
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise LongContextSpoolError("spool object owner or mode is untrusted")


def _positive(value: int, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise LongContextSpoolError(f"invalid {name}")
    return value


def _digest(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise LongContextSpoolError(f"invalid {name}")
    return value


def _volume_available_bytes(fd: int) -> int:
    """Fail closed on malformed kernel volume counters before disk admission.

    A capacity diagnostic and the actual durable publication must use exactly
    the same validation: multiplication alone can turn two negative counters
    into a falsely positive allocation budget.
    """
    try:
        volume = os.fstatvfs(fd)
        blocks, block_size = volume.f_bavail, volume.f_frsize
    except (OSError, ValueError, OverflowError, AttributeError, TypeError) as exc:
        raise LongContextSpoolError("spool volume telemetry unavailable") from exc
    if (type(blocks) is not int or not 0 <= blocks <= 2**63 - 1
            or type(block_size) is not int
            or not 1 <= block_size <= 2**63 - 1):
        raise LongContextSpoolError("invalid spool volume telemetry")
    available = blocks * block_size
    if available > 2**127 - 1:
        raise LongContextSpoolError("invalid spool volume telemetry")
    return available


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LongContextSpoolError("duplicate checkpoint key")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class SpoolCheckpoint:
    schema: str
    sequence_digest: str
    object_digest: str
    tokenizer_digest: str
    cursor: int
    parent_digest: str | None
    digest: str

    def __post_init__(self) -> None:
        if self.schema != _SCHEMA:
            raise LongContextSpoolError("unsupported checkpoint schema")
        for name in ("sequence_digest", "object_digest", "tokenizer_digest", "digest"):
            _digest(getattr(self, name), name)
        if self.parent_digest is not None:
            _digest(self.parent_digest, "parent_digest")
        if isinstance(self.cursor, bool) or not isinstance(self.cursor, int) or self.cursor < 0:
            raise LongContextSpoolError("invalid cursor")
        if self.parent_digest is None and self.cursor != 0:
            raise LongContextSpoolError("genesis cursor must be zero")
        if self.parent_digest == self.digest:
            raise LongContextSpoolError("self-referential checkpoint")

    def body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "sequence_digest": self.sequence_digest,
            "object_digest": self.object_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "cursor": self.cursor,
            "parent_digest": self.parent_digest,
        }



def _open_directory_chain(path: Path, *, create: bool) -> int:
    """Open every POSIX ancestor without following any path component.

    mkdir is descriptor-relative so a concurrently replaced ancestor cannot
    redirect subsequent creates. The caller owns the returned directory FD.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise LongContextSpoolError("secure POSIX directory operations unavailable")
    absolute = Path(os.path.abspath(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parts = absolute.parts
    fd = os.open(parts[0], flags)
    try:
        for component in parts[1:]:
            if component in {"", ".", ".."}:
                raise LongContextSpoolError("invalid spool directory component")
            if create:
                try:
                    os.mkdir(component, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _selected_source_identity(info: os.stat_result) -> tuple[int, ...]:
    """Descriptor identity plus mutation metadata; never trust path alone."""
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def _read_stable_selected_fd(fd: int, *, limit: int) -> tuple[bytes, os.stat_result]:
    """Bound reads and reject source changes observed during materialization."""
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise LongContextSpoolError("sequence source is not regular")
    if before.st_size < 0 or before.st_size > limit:
        raise LongContextSpoolError("selected token sequence exceeds byte budget")
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        part = os.read(fd, min(_CHUNK, remaining))
        if not part:
            break
        chunks.append(part)
        remaining -= len(part)
    after = os.fstat(fd)
    if _selected_source_identity(before) != _selected_source_identity(after):
        raise LongContextSpoolError("selected sequence changed during read")
    raw = b"".join(chunks)
    if len(raw) > limit or len(raw) != before.st_size:
        raise LongContextSpoolError("selected sequence size changed during read")
    return raw, before


def read_selected_sequence(path: Path, *, limit: int) -> bytes:
    """Read a bounded selected token file with POSIX inode/name fencing.

    A selected file replaced during reading cannot silently become the
    source of an acknowledged checkpoint. Same-UID hostile filesystem writers
    remain outside this local spool's authorization boundary. Windows lacks
    the descriptor-relative final-name fence and is not security-qualified.
    """
    _positive(limit, "sequence byte limit", MAX_SERIALIZED_SEQUENCE_BYTES)
    if os.name != "posix":
        if path.is_symlink():
            raise LongContextSpoolError("symlinked sequence source rejected")
        with path.open("rb") as stream:
            raw, _ = _read_stable_selected_fd(stream.fileno(), limit=limit)
        return raw
    parent_fd = _open_directory_chain(path.parent, create=False)
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path.name, flags, dir_fd=parent_fd)
        try:
            raw, before = _read_stable_selected_fd(fd, limit=limit)
            # Resolve the final name only against the pinned parent directory,
            # not against a path that can be redirected by ancestor mutation.
            named = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            if _selected_source_identity(named) != _selected_source_identity(before):
                raise LongContextSpoolError("selected sequence path changed during read")
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)

class LongContextSpool:
    """Content-addressed offline token store with immutable progress receipts.

    Only operator-owned directories are supported. A completed atomic publish
    survives process restart; an interrupted publish leaves only a disposable
    hidden temporary file. No implicit latest pointer or cross-process lease
    exists, so concurrent branches of progress never overwrite one another.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        max_sequence_bytes: int = MAX_SERIALIZED_SEQUENCE_BYTES,
        max_window_tokens: int = DEFAULT_WINDOW_TOKENS,
        disk_reserve_bytes: int = 128 * 1024 * 1024,
        max_spool_bytes: int = _DEFAULT_SPOOL_QUOTA_BYTES,
    ) -> None:
        _positive(max_sequence_bytes, "max_sequence_bytes", MAX_SERIALIZED_SEQUENCE_BYTES)
        _positive(max_window_tokens, "max_window_tokens", MAX_WINDOW_TOKENS)
        if (isinstance(disk_reserve_bytes, bool) or not isinstance(disk_reserve_bytes, int)
                or not 0 <= disk_reserve_bytes <= 2**63 - 1):
            raise LongContextSpoolError("invalid disk reserve")
        _positive(max_spool_bytes, "max_spool_bytes", _MAX_SPOOL_QUOTA_BYTES)
        self.max_spool_bytes = max_spool_bytes
        self._owner_pid = os.getpid()
        self.root = Path(os.path.abspath(directory)) if os.name == "posix" else Path(directory)
        self.max_sequence_bytes = max_sequence_bytes
        self.max_window_tokens = max_window_tokens
        self.disk_reserve_bytes = disk_reserve_bytes
        self.objects = self.root / "objects"
        self.checkpoints = self.root / "checkpoints"
        self._root_fd: int | None = None
        try:
            if os.name == "posix":
                root_fd = _open_directory_chain(self.root, create=True)
                try:
                    info = os.fstat(root_fd)
                    if (not stat.S_ISDIR(info.st_mode)
                            or info.st_uid != os.geteuid()
                            or stat.S_IMODE(info.st_mode) != 0o700):
                        raise LongContextSpoolError("insecure spool root permissions")
                    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                    for name in ("objects", "checkpoints"):
                        try:
                            os.mkdir(name, 0o700, dir_fd=root_fd)
                        except FileExistsError:
                            pass
                        child_fd = os.open(name, flags, dir_fd=root_fd)
                        try:
                            info = os.fstat(child_fd)
                            if (not stat.S_ISDIR(info.st_mode)
                                    or info.st_uid != os.geteuid()
                                    or stat.S_IMODE(info.st_mode) != 0o700):
                                raise LongContextSpoolError("insecure spool component")
                        finally:
                            os.close(child_fd)
                    self._root_fd = root_fd
                except BaseException:
                    os.close(root_fd)
                    raise
            else:
                # Windows lacks the descriptor-relative no-follow primitive
                # used above. The path mode is explicitly unqualified against
                # same-user ancestor replacement and must not be called secure.
                if self.root.is_symlink():
                    raise LongContextSpoolError("spool root must not be a symlink")
                self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
                if not self.root.is_dir() or self.root.is_symlink():
                    raise LongContextSpoolError("spool root must be a directory")
                for child in (self.objects, self.checkpoints):
                    if child.is_symlink():
                        raise LongContextSpoolError("spool component must not be a symlink")
                    child.mkdir(mode=0o700, exist_ok=True)
                    if not child.is_dir() or child.is_symlink():
                        raise LongContextSpoolError("spool component must be a directory")
        except OSError as exc:
            raise LongContextSpoolError("cannot initialize pinned spool directory") from exc

    def _require_owner_process(self) -> None:
        """An inherited directory descriptor is not a new process grant."""
        try:
            current = os.getpid()
        except BaseException as exc:
            raise LongContextSpoolError("spool process identity unavailable") from exc
        if type(current) is not int or current != self._owner_pid:
            raise LongContextSpoolError("forked spool requires new owner authorization")

    def close(self) -> None:
        fd = getattr(self, "_root_fd", None)
        self._root_fd = None
        if fd is not None:
            os.close(fd)

    def __del__(self) -> None:
        try:
            self.close()
        except OSError:
            pass

    def _open_bucket(self, kind: str, digest: str) -> int:
        self._require_owner_process()
        if self._root_fd is None:
            raise LongContextSpoolError("secure spool root is closed")
        _digest(digest, "content digest")
        if kind not in {"object", "checkpoint"}:
            raise LongContextSpoolError("unknown spool object kind")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        base_name = "objects" if kind == "object" else "checkpoints"
        try:
            base_fd = os.open(base_name, flags, dir_fd=self._root_fd)
            try:
                base_info = os.fstat(base_fd)
                if (base_info.st_uid != os.geteuid()
                        or stat.S_IMODE(base_info.st_mode) != 0o700):
                    raise LongContextSpoolError("insecure spool component")
                try:
                    os.mkdir(digest[:2], 0o700, dir_fd=base_fd)
                except FileExistsError:
                    pass
                bucket_fd = os.open(digest[:2], flags, dir_fd=base_fd)
                bucket_info = os.fstat(bucket_fd)
                if (bucket_info.st_uid != os.geteuid()
                        or stat.S_IMODE(bucket_info.st_mode) != 0o700):
                    os.close(bucket_fd)
                    raise LongContextSpoolError("insecure spool bucket")
                return bucket_fd
            finally:
                os.close(base_fd)
        except OSError as exc:
            raise LongContextSpoolError("secure spool bucket unavailable") from exc

    def _read_exact_fd(self, path: Path, *, limit: int) -> bytes:
        try:
            parts = path.relative_to(self.root).parts
        except ValueError as exc:
            raise LongContextSpoolError("spool path escaped pinned root") from exc
        if len(parts) != 3 or parts[0] not in {"objects", "checkpoints"}:
            raise LongContextSpoolError("invalid spool path shape")
        digest = _digest(parts[2], "content digest")
        if parts[1] != digest[:2]:
            raise LongContextSpoolError("spool bucket identity mismatch")
        kind = "object" if parts[0] == "objects" else "checkpoint"
        bucket_fd = self._open_bucket(kind, digest)
        try:
            flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            fd = os.open(digest, flags, dir_fd=bucket_fd)
            try:
                _require_private_spool_file(fd)
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(limit + 1)
            finally:
                os.close(fd)
            if len(raw) > limit:
                raise LongContextSpoolError("spool object exceeds byte budget")
            return raw
        except OSError as exc:
            raise LongContextSpoolError("secure spool read failed") from exc
        finally:
            os.close(bucket_fd)

    def _publication_lock(self) -> int:
        """Bounded cross-process lock for cooperative POSIX disk admissions.

        Lock before checking free space and hold through durable publication.
        This prevents *cooperating* spool writers from each independently
        spending the same disk reserve. The trusted owner must still enforce
        per-tenant quotas and exclude malicious same-UID directory mutation.
        """
        self._require_owner_process()
        if self._root_fd is None:
            raise LongContextSpoolError("secure spool root is closed")
        import fcntl

        try:
            fd = os.open(
                ".publish.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                0o600, dir_fd=self._root_fd,
            )
        except OSError as exc:
            raise LongContextSpoolError("spool publication lock unavailable") from exc
        try:
            _require_private_spool_file(fd)
            identity = os.fstat(fd)
            if identity.st_nlink != 1:
                raise LongContextSpoolError("spool publication lock has external links")
            started = monotonic_ns()
            if type(started) is not int or started < 0:
                raise LongContextSpoolError("invalid spool lock clock")
            # An unavailable/frozen clock must not turn a busy local writer
            # into an unbounded wait. The attempt cap is independent of time.
            attempts = 0
            max_attempts = _PUBLISH_LOCK_WAIT_NS // 10_000_000 + 1
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    attempts += 1
                    now = monotonic_ns()
                    if type(now) is not int or now < started:
                        raise LongContextSpoolError(
                            "spool lock monotonic clock unavailable or regressed"
                        ) from exc
                    if (now - started >= _PUBLISH_LOCK_WAIT_NS
                            or attempts >= max_attempts):
                        raise LongContextSpoolError(
                            "spool publication lock contention"
                        ) from exc
                    sleep(0.01)
            # An unlinked/replaced lock inode cannot serialize new writers.
            # Recheck the descriptor-relative name AFTER acquiring the lock.
            entry = os.stat(
                ".publish.lock", dir_fd=self._root_fd, follow_symlinks=False,
            )
            if ((entry.st_dev, entry.st_ino) !=
                    (identity.st_dev, identity.st_ino) or entry.st_nlink != 1):
                raise LongContextSpoolError("spool publication lock replaced")
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _publish_fd(self, kind: str, digest: str, raw: bytes) -> None:
        lock_fd = self._publication_lock()
        try:
            self._publish_fd_locked(kind, digest, raw)
        finally:
            os.close(lock_fd)


    @staticmethod
    def _reap_temp_locked(
        bucket_fd: int, digest: str, *, max_entries: int, max_bytes: int,
    ) -> dict[str, int | bool | str]:
        """Recover only known-digest orphan temps under the publication lock.

        A crashed writer can leave either a single-link partial temp or a
        two-link temp already published at the final content address. Both
        cases are verified by inode, owner, permissions and link count before
        unlink. No arbitrary directory cleanup or wildcard deletion occurs.
        """
        _digest(digest, "content digest")
        _positive(max_entries, "max_entries", _RECOVERY_MAX_ENTRIES)
        _positive(max_bytes, "max_bytes", _RECOVERY_MAX_BYTES)
        prefix = "." + digest + "."
        suffix = ".tmp"
        matches: list[str] = []
        scanned = 0
        try:
            with os.scandir(bucket_fd) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > _RECOVERY_MAX_SCAN:
                        raise LongContextSpoolError("spool recovery scan bound exceeded")
                    name = entry.name
                    if (name.startswith(prefix) and name.endswith(suffix)
                            and len(name) == len(prefix) + 16 + len(suffix)
                            and all(ch in "0123456789abcdef"
                                    for ch in name[len(prefix):-len(suffix)])):
                        matches.append(name)
                        if len(matches) > max_entries:
                            raise LongContextSpoolError("spool recovery entry bound exceeded")
        except OSError as exc:
            raise LongContextSpoolError("spool recovery enumeration failed") from exc
        # Preflight every candidate before unlinking any. A corrupt later
        # entry or exhausted budget must not cause partial recovery.
        preflight: dict[str, tuple[int, int, int, int]] = {}
        total_bytes = 0
        for name in sorted(matches):
            try:
                info = os.stat(name, dir_fd=bucket_fd, follow_symlinks=False)
                if (not stat.S_ISREG(info.st_mode)
                        or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) != 0o600
                        or info.st_nlink not in (1, 2)
                        or info.st_size < 0
                        or info.st_size > MAX_SERIALIZED_SEQUENCE_BYTES + 4096):
                    raise LongContextSpoolError("untrusted orphan spool object")
                total_bytes += info.st_size
                if total_bytes > max_bytes:
                    raise LongContextSpoolError("spool recovery byte bound exceeded")
                if info.st_nlink == 2:
                    final = os.stat(
                        digest, dir_fd=bucket_fd, follow_symlinks=False,
                    )
                    if (final.st_dev, final.st_ino) != (info.st_dev, info.st_ino):
                        raise LongContextSpoolError("untrusted orphan hardlink")
                preflight[name] = (
                    info.st_dev, info.st_ino, info.st_nlink, info.st_size,
                )
            except OSError as exc:
                raise LongContextSpoolError("orphan spool preflight denied") from exc
        reclaimed = 0
        inspected_bytes = 0
        removed = 0
        for name in sorted(matches):
            flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            try:
                fd = os.open(name, flags, dir_fd=bucket_fd)
                try:
                    info = os.fstat(fd)
                    if (not stat.S_ISREG(info.st_mode)
                            or info.st_uid != os.geteuid()
                            or stat.S_IMODE(info.st_mode) != 0o600
                            or info.st_nlink not in (1, 2)
                            or info.st_size < 0
                            or info.st_size > MAX_SERIALIZED_SEQUENCE_BYTES + 4096):
                        raise LongContextSpoolError("untrusted orphan spool object")
                    if ((info.st_dev, info.st_ino, info.st_nlink, info.st_size)
                            != preflight[name]):
                        raise LongContextSpoolError("orphan spool changed after preflight")
                    if inspected_bytes + info.st_size > max_bytes:
                        raise LongContextSpoolError("spool recovery byte bound exceeded")
                    inspected_bytes += info.st_size
                    if info.st_nlink == 2:
                        # A completed link() before a crash leaves a second
                        # name for the *same* inode. Any other link is denied.
                        final = os.stat(
                            digest, dir_fd=bucket_fd, follow_symlinks=False,
                        )
                        if ((final.st_dev, final.st_ino) !=
                                (info.st_dev, info.st_ino)):
                            raise LongContextSpoolError("untrusted orphan hardlink")
                    current = os.stat(
                        name, dir_fd=bucket_fd, follow_symlinks=False,
                    )
                    if ((current.st_dev, current.st_ino, current.st_nlink) !=
                            (info.st_dev, info.st_ino, info.st_nlink)):
                        raise LongContextSpoolError("orphan spool inode changed")
                    os.unlink(name, dir_fd=bucket_fd)
                    reclaimed += info.st_size if info.st_nlink == 1 else 0
                    removed += 1
                finally:
                    os.close(fd)
            except OSError as exc:
                raise LongContextSpoolError("orphan spool recovery denied") from exc
        if removed:
            try:
                os.fsync(bucket_fd)
            except OSError as exc:
                raise LongContextSpoolError("orphan spool recovery fsync failed") from exc
        return {
            "schema": "skeleton.ai.long-context-temp-recovery.v1",
            "removed": removed,
            "bytes_reclaimed": reclaimed,
            "complete": True,
        }

    def recover_abandoned_temps(
        self, *, kind: str, digest: str,
        max_entries: int = _RECOVERY_MAX_ENTRIES,
        max_bytes: int = _RECOVERY_MAX_BYTES,
    ) -> dict[str, int | bool | str]:
        """Explicit, bounded crash recovery for a known content digest.

        Requires the same cooperative publication lock as normal writers.
        Does not recover arbitrary tenant files or certify trusted publishers.
        """
        if os.name != "posix":
            raise LongContextSpoolError("POSIX orphan recovery not qualified")
        lock_fd = self._publication_lock()
        try:
            bucket_fd = self._open_bucket(kind, digest)
            try:
                return self._reap_temp_locked(
                    bucket_fd, digest,
                    max_entries=max_entries, max_bytes=max_bytes,
                )
            finally:
                os.close(bucket_fd)
        finally:
            os.close(lock_fd)

    def _spool_usage_locked(self) -> int:
        """Bounded POSIX inventory under the cooperative publication lock.

        Account for all regular files in both content trees, including
        abandoned temps. Hardlinked temp/final names count once by inode.
        Unknown entries or an oversized inventory deny admission rather than
        assuming free capacity. This is not an adversarial same-UID quota.
        """
        self._require_owner_process()
        if os.name != "posix" or self._root_fd is None:
            raise LongContextSpoolError("secure spool quota inventory unavailable")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        scanned = 0
        total = 0
        seen: set[tuple[int, int]] = set()
        try:
            for root_name in ("objects", "checkpoints"):
                base_fd = os.open(root_name, flags, dir_fd=self._root_fd)
                try:
                    base = os.fstat(base_fd)
                    if (base.st_uid != os.geteuid()
                            or stat.S_IMODE(base.st_mode) != 0o700):
                        raise LongContextSpoolError("untrusted spool quota root")
                    with os.scandir(base_fd) as buckets:
                        for bucket in buckets:
                            scanned += 1
                            if scanned > _QUOTA_MAX_ENTRIES:
                                raise LongContextSpoolError("spool quota scan bound exceeded")
                            name = bucket.name
                            if (len(name) != 2 or
                                    any(c not in "0123456789abcdef" for c in name)):
                                raise LongContextSpoolError("untrusted spool quota bucket")
                            bucket_fd = os.open(name, flags, dir_fd=base_fd)
                            try:
                                info = os.fstat(bucket_fd)
                                if (info.st_uid != os.geteuid()
                                        or stat.S_IMODE(info.st_mode) != 0o700):
                                    raise LongContextSpoolError("untrusted spool quota bucket")
                                with os.scandir(bucket_fd) as entries:
                                    for entry in entries:
                                        scanned += 1
                                        if scanned > _QUOTA_MAX_ENTRIES:
                                            raise LongContextSpoolError(
                                                "spool quota scan bound exceeded"
                                            )
                                        item = os.stat(
                                            entry.name, dir_fd=bucket_fd,
                                            follow_symlinks=False,
                                        )
                                        if (not stat.S_ISREG(item.st_mode)
                                                or item.st_uid != os.geteuid()
                                                or stat.S_IMODE(item.st_mode) != 0o600
                                                or item.st_nlink not in (1, 2)
                                                or item.st_size < 0):
                                            raise LongContextSpoolError(
                                                "untrusted spool quota object"
                                            )
                                        inode = (item.st_dev, item.st_ino)
                                        if inode not in seen:
                                            seen.add(inode)
                                            total += item.st_size
                                            if total > self.max_spool_bytes:
                                                raise LongContextSpoolError(
                                                    "spool byte quota exhausted"
                                                )
                            finally:
                                os.close(bucket_fd)
                finally:
                    os.close(base_fd)
        except OSError as exc:
            raise LongContextSpoolError("spool quota inventory failed") from exc
        return total

    def capacity_snapshot(self, *, requested_bytes: int = 0) -> dict[str, int | str | bool]:
        """Bounded payload-free POSIX admission observation, never a lease.

        The same cross-process lock used by publication serializes this scan
        against cooperating writers. The result is a point-in-time diagnostic:
        callers MUST still use guarded publication and recheck disk pressure.
        Unknown or malformed volume telemetry fails closed.
        """
        self._require_owner_process()
        if (type(requested_bytes) is not int or requested_bytes < 0
                or requested_bytes > _MAX_SPOOL_QUOTA_BYTES):
            raise LongContextSpoolError("invalid requested_bytes")
        if os.name != "posix" or self._root_fd is None:
            raise LongContextSpoolError("secure spool capacity observation unavailable")
        lock_fd = self._publication_lock()
        try:
            used = self._spool_usage_locked()
            available = _volume_available_bytes(self._root_fd)
            remaining_quota = self.max_spool_bytes - used
            disk_headroom = max(0, available - self.disk_reserve_bytes)
            publishable = min(remaining_quota, disk_headroom)
            sufficient = publishable >= requested_bytes if requested_bytes else publishable > 0
            return {
                "schema": "skeleton.ai.long-context-capacity.v1",
                "used_bytes": used,
                "quota_bytes": self.max_spool_bytes,
                "quota_remaining_bytes": remaining_quota,
                "volume_available_bytes": available,
                "disk_reserve_bytes": self.disk_reserve_bytes,
                "observed_publishable_bytes": publishable,
                "requested_bytes": requested_bytes,
                "request_observed_sufficient": sufficient,
                "state": "observed_available" if sufficient else "hold",
                "is_admission_lease": False,
                "hardware_qualification": "not_assessed",
            }
        finally:
            os.close(lock_fd)

    def _publish_fd_locked(self, kind: str, digest: str, raw: bytes) -> None:
        """Caller holds the cross-process admission lock."""
        bucket_fd = self._open_bucket(kind, digest)
        try:
            # A prior crash may leave a temp after link() but before unlink().
            # Recover it under the same lock before checking final content.
            self._reap_temp_locked(
                bucket_fd, digest,
                max_entries=_RECOVERY_MAX_ENTRIES,
                max_bytes=_RECOVERY_MAX_BYTES,
            )
            try:
                existing = os.open(
                    digest, os.O_RDONLY | os.O_NOFOLLOW |
                    getattr(os, "O_NONBLOCK", 0), dir_fd=bucket_fd,
                )
            except FileNotFoundError:
                existing = None
            if existing is not None:
                try:
                    _require_private_spool_file(existing)
                    with os.fdopen(existing, "rb", closefd=False) as stream:
                        observed = stream.read(len(raw) + 1)
                    if observed != raw:
                        raise LongContextSpoolError("existing immutable object mismatch")
                    return
                finally:
                    os.close(existing)
            used = self._spool_usage_locked()
            if len(raw) > self.max_spool_bytes - used:
                raise LongContextSpoolError("spool byte quota prevents admission")
            free = _volume_available_bytes(bucket_fd)
            if free < self.disk_reserve_bytes or free - self.disk_reserve_bytes < len(raw):
                raise LongContextSpoolError("disk reserve prevents spool admission")
            temp = "." + digest + "." + os.urandom(8).hex() + ".tmp"
            fd = os.open(
                temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=bucket_fd,
            )
            try:
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(fd)
                # The name may be replaced even while our writer FD stays
                # pinned. Verify both the temporary name and inode BEFORE
                # linking, then verify the final link against the same FD.
                writer_info = os.fstat(fd)
                temp_info = os.stat(temp, dir_fd=bucket_fd, follow_symlinks=False)
                if (not stat.S_ISREG(writer_info.st_mode)
                        or not stat.S_ISREG(temp_info.st_mode)
                        or writer_info.st_uid != os.geteuid()
                        or stat.S_IMODE(writer_info.st_mode) != 0o600
                        or writer_info.st_nlink != 1
                        or writer_info.st_size != len(raw)
                        or (writer_info.st_dev, writer_info.st_ino)
                        != (temp_info.st_dev, temp_info.st_ino)):
                    raise LongContextSpoolError("publication temp inode replaced")
                try:
                    os.link(
                        temp, digest, src_dir_fd=bucket_fd,
                        dst_dir_fd=bucket_fd, follow_symlinks=False,
                    )
                except FileExistsError:
                    existing = os.open(
                        digest, os.O_RDONLY | os.O_NOFOLLOW |
                        getattr(os, "O_NONBLOCK", 0), dir_fd=bucket_fd,
                    )
                    try:
                        _require_private_spool_file(existing)
                        with os.fdopen(existing, "rb", closefd=False) as stream:
                            observed = stream.read(len(raw) + 1)
                        if observed != raw:
                            raise LongContextSpoolError("concurrent immutable object mismatch")
                    finally:
                        os.close(existing)
                else:
                    # The link operation can race a same-UID replacement of
                    # the temp name. Never certify a final inode other than
                    # the writer FD, even if a pathname lookup succeeded.
                    published = os.open(
                        digest, os.O_RDONLY | os.O_NOFOLLOW |
                        getattr(os, "O_NONBLOCK", 0), dir_fd=bucket_fd,
                    )
                    try:
                        published_info = os.fstat(published)
                        writer_info = os.fstat(fd)
                        if (not stat.S_ISREG(published_info.st_mode)
                                or (published_info.st_dev, published_info.st_ino)
                                != (writer_info.st_dev, writer_info.st_ino)
                                or published_info.st_nlink != 2
                                or writer_info.st_size != len(raw)):
                            raise LongContextSpoolError(
                                "published spool inode mismatch"
                            )
                    finally:
                        os.close(published)
                os.fsync(bucket_fd)
            finally:
                # Do not unlink a replacement temp name: preserve evidence
                # and fail closed rather than deleting a different inode.
                writer_info = os.fstat(fd)
                os.close(fd)
                try:
                    cleanup_info = os.stat(
                        temp, dir_fd=bucket_fd, follow_symlinks=False,
                    )
                except FileNotFoundError as exc:
                    raise LongContextSpoolError(
                        "publication temp vanished; recovery required"
                    ) from exc
                if ((cleanup_info.st_dev, cleanup_info.st_ino)
                        != (writer_info.st_dev, writer_info.st_ino)):
                    raise LongContextSpoolError(
                        "publication temp replaced; recovery required"
                    )
                os.unlink(temp, dir_fd=bucket_fd)
                # The second directory sync durably removes the temporary
                # hardlink. A crash before this point is recoverable by the
                # bounded orphan-temp scanner.
                os.fsync(bucket_fd)
        except OSError as exc:
            raise LongContextSpoolError("secure spool publication failed") from exc
        finally:
            os.close(bucket_fd)

    def _path(self, kind: str, digest: str) -> Path:
        _digest(digest, "content digest")
        base = self.objects if kind == "object" else self.checkpoints
        return base / digest[:2] / digest

    def _read_exact(self, path: Path, *, limit: int) -> bytes:
        self._require_owner_process()
        if os.name == "posix":
            return self._read_exact_fd(path, limit=limit)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            if path.is_symlink():
                raise LongContextSpoolError("symlinked spool object rejected")
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise LongContextSpoolError("spool object is not a regular file")
                raw = stream.read(limit + 1)
        except OSError as exc:
            raise LongContextSpoolError("spool object unavailable") from exc
        if len(raw) > limit:
            raise LongContextSpoolError("spool object exceeds byte budget")
        return raw

    def _publish(self, kind: str, digest: str, raw: bytes) -> None:
        self._require_owner_process()
        if os.name == "posix":
            self._publish_fd(kind, digest, raw)
            return
        path = self._path(kind, digest)
        try:
            if path.parent.is_symlink():
                raise LongContextSpoolError("symlinked spool bucket rejected")
            path.parent.mkdir(mode=0o700, exist_ok=True)
            if path.parent.is_symlink():
                raise LongContextSpoolError("symlinked spool bucket rejected")
            if path.exists() or path.is_symlink():
                if self._read_exact(path, limit=len(raw)) != raw:
                    raise LongContextSpoolError("existing immutable object mismatch")
                return
            free = shutil.disk_usage(self.root).free
            if free < self.disk_reserve_bytes or free - self.disk_reserve_bytes < len(raw):
                raise LongContextSpoolError("disk reserve prevents spool admission")
            temp = path.with_name("." + digest + "." + os.urandom(8).hex() + ".tmp")
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                with os.fdopen(os.open(temp, flags, 0o600), "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temp, path, follow_symlinks=False)
                except FileExistsError:
                    if self._read_exact(path, limit=len(raw)) != raw:
                        raise LongContextSpoolError("concurrent immutable object mismatch")
                if os.name == "posix":
                    fd = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
            finally:
                temp.unlink(missing_ok=True)
        except OSError as exc:
            raise LongContextSpoolError("spool publication failed") from exc

    @staticmethod
    def _checkpoint(
        sequence: TokenSequence,
        object_digest: str,
        cursor: int,
        parent_digest: str | None,
    ) -> SpoolCheckpoint:
        body = {
            "schema": _SCHEMA,
            "sequence_digest": sequence.digest,
            "object_digest": object_digest,
            "tokenizer_digest": sequence.tokenizer_digest,
            "cursor": cursor,
            "parent_digest": parent_digest,
        }
        return SpoolCheckpoint(**body, digest=sha256(_canonical(body)).hexdigest())

    def _publish_checkpoint(self, checkpoint: SpoolCheckpoint) -> str:
        self._publish("checkpoint", checkpoint.digest, _canonical(asdict(checkpoint)))
        return checkpoint.digest

    def stage(self, sequence: TokenSequence) -> str:
        self._require_owner_process()
        """Persist canonical token IDs and return a deterministic genesis receipt."""
        if not isinstance(sequence, TokenSequence):
            raise LongContextSpoolError("TokenSequence required")
        try:
            raw = serialize_token_sequence(sequence)
        except TokenizerContractError as exc:
            raise LongContextSpoolError("sequence cannot be serialized") from exc
        if len(raw) > self.max_sequence_bytes:
            raise LongContextSpoolError("sequence exceeds spool budget")
        object_digest = sha256(raw).hexdigest()
        self._publish("object", object_digest, raw)
        return self._publish_checkpoint(self._checkpoint(sequence, object_digest, 0, None))

    def _read_checkpoint(self, digest: str) -> SpoolCheckpoint:
        raw = self._read_exact(self._path("checkpoint", digest), limit=4096)
        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(LongContextSpoolError("nonfinite checkpoint value")))
            if not isinstance(data, dict) or set(data) != {
                "schema", "sequence_digest", "object_digest", "tokenizer_digest",
                "cursor", "parent_digest", "digest",
            }:
                raise LongContextSpoolError("checkpoint shape mismatch")
            checkpoint = SpoolCheckpoint(**data)
        except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
            raise LongContextSpoolError("invalid checkpoint encoding") from exc
        if checkpoint.digest != digest or sha256(_canonical(checkpoint.body())).hexdigest() != digest:
            raise LongContextSpoolError("checkpoint integrity mismatch")
        if _canonical(asdict(checkpoint)) != raw:
            raise LongContextSpoolError("noncanonical checkpoint")
        return checkpoint

    def load(
        self, checkpoint_digest: str, *, expected_tokenizer_digest: str,
    ) -> tuple[SpoolCheckpoint, TokenSequence]:
        """Verify checkpoint and sequence before returning any token content."""
        self._require_owner_process()
        _digest(expected_tokenizer_digest, "expected_tokenizer_digest")
        checkpoint = self._read_checkpoint(checkpoint_digest)
        if checkpoint.tokenizer_digest != expected_tokenizer_digest:
            raise LongContextSpoolError("tokenizer identity mismatch")
        raw = self._read_exact(self._path("object", checkpoint.object_digest),
                               limit=self.max_sequence_bytes)
        if sha256(raw).hexdigest() != checkpoint.object_digest:
            raise LongContextSpoolError("stored sequence integrity mismatch")
        try:
            sequence = deserialize_token_sequence(raw, require_canonical=True)
        except TokenizerContractError as exc:
            raise LongContextSpoolError("stored token sequence invalid") from exc
        if (sequence.digest != checkpoint.sequence_digest
                or sequence.tokenizer_digest != checkpoint.tokenizer_digest
                or checkpoint.cursor > len(sequence.token_ids)):
            raise LongContextSpoolError("checkpoint does not bind sequence")
        if checkpoint.parent_digest is not None:
            parent = self._read_checkpoint(checkpoint.parent_digest)
            if (parent.sequence_digest != checkpoint.sequence_digest
                    or parent.object_digest != checkpoint.object_digest
                    or parent.tokenizer_digest != checkpoint.tokenizer_digest
                    or parent.cursor >= checkpoint.cursor):
                raise LongContextSpoolError("checkpoint ancestry mismatch")
        return checkpoint, sequence

    def audit_history(
        self, checkpoint_digest: str, *, expected_tokenizer_digest: str,
        max_checkpoints: int = 4096,
    ) -> dict[str, object]:
        """Verify the entire immutable ancestry up to a bounded genesis.

        No token bytes are returned. This is a custody/integrity audit, not
        proof of trusted publisher identity or a cross-process replay fence.
        A chain longer than the bound fails closed rather than claiming a
        complete audit. The caller must retain its trusted latest digest.
        """
        self._require_owner_process()
        _digest(checkpoint_digest, "checkpoint_digest")
        _digest(expected_tokenizer_digest, "expected_tokenizer_digest")
        _positive(max_checkpoints, "max_checkpoints", 100_000)
        seen: set[str] = set()
        current = checkpoint_digest
        newest: SpoolCheckpoint | None = None
        previous: SpoolCheckpoint | None = None
        for depth in range(max_checkpoints):
            if current in seen:
                raise LongContextSpoolError("checkpoint ancestry cycle")
            seen.add(current)
            item = self._read_checkpoint(current)
            if item.tokenizer_digest != expected_tokenizer_digest:
                raise LongContextSpoolError("checkpoint tokenizer drift")
            if newest is None:
                newest = item
                # The content digest must still match the source sequence.
                self.load(current, expected_tokenizer_digest=expected_tokenizer_digest)
            elif (item.sequence_digest != newest.sequence_digest
                  or item.object_digest != newest.object_digest
                  or item.tokenizer_digest != newest.tokenizer_digest):
                raise LongContextSpoolError("checkpoint ancestry identity drift")
            if previous is not None and item.cursor >= previous.cursor:
                raise LongContextSpoolError("checkpoint ancestry cursor rollback")
            if item.parent_digest is None:
                if item.cursor != 0:
                    raise LongContextSpoolError("checkpoint genesis is not zero")
                return {
                    "schema": "skeleton.ai.long-context-history-audit.v1",
                    "checkpoint_digest": checkpoint_digest,
                    "genesis_digest": current,
                    "checkpoints_verified": depth + 1,
                    "cursor": newest.cursor,
                    "complete": True,
                    "trusted_publisher_attested": False,
                    "replay_fence_attested": False,
                }
            previous = item
            current = item.parent_digest
        raise LongContextSpoolError("checkpoint ancestry exceeds audit bound")

    def next_window(
        self, checkpoint_digest: str, *, expected_tokenizer_digest: str, max_tokens: int,
    ) -> TokenWindow | None:
        # Never materialize an unbounded token tuple in the application.
        # This per-instance limit is intentionally independent of the full
        # serialized context length and applies after process restart.
        self._require_owner_process()
        _positive(max_tokens, "max_tokens", self.max_window_tokens)
        checkpoint, sequence = self.load(
            checkpoint_digest, expected_tokenizer_digest=expected_tokenizer_digest,
        )
        if checkpoint.cursor == len(sequence.token_ids):
            return None
        stop = min(len(sequence.token_ids), checkpoint.cursor + max_tokens)
        return TokenWindow(
            checkpoint.cursor, stop, tuple(sequence.token_ids[checkpoint.cursor:stop]),
            sequence.digest,
        )

    def audited_next_window(
        self, checkpoint_digest: str, *, expected_tokenizer_digest: str,
        max_tokens: int, max_checkpoints: int = 4096,
    ) -> TokenWindow | None:
        """Require complete bounded ancestry proof before releasing token IDs.

        Unlike next_window, this rejects a missing or corrupted *grandparent*
        checkpoint. It does not authenticate a publisher or establish a global
        replay fence. The operator must supply a trusted checkpoint digest.
        """
        self._require_owner_process()
        _positive(max_tokens, "max_tokens", self.max_window_tokens)
        self.audit_history(
            checkpoint_digest, expected_tokenizer_digest=expected_tokenizer_digest,
            max_checkpoints=max_checkpoints,
        )
        return self.next_window(
            checkpoint_digest, expected_tokenizer_digest=expected_tokenizer_digest,
            max_tokens=max_tokens,
        )

    def audited_advance(
        self, checkpoint_digest: str, *, expected_tokenizer_digest: str,
        consumed_tokens: int, max_checkpoints: int = 4096,
    ) -> str:
        """Reject broken ancestry before committing any new progress."""
        self._require_owner_process()
        _positive(consumed_tokens, "consumed_tokens", 2**31 - 1)
        self.audit_history(
            checkpoint_digest, expected_tokenizer_digest=expected_tokenizer_digest,
            max_checkpoints=max_checkpoints,
        )
        return self.advance(
            checkpoint_digest, expected_tokenizer_digest=expected_tokenizer_digest,
            consumed_tokens=consumed_tokens,
        )

    def advance(
        self, checkpoint_digest: str, *, expected_tokenizer_digest: str, consumed_tokens: int,
    ) -> str:
        """Commit actual progress as a new immutable child; never rewrite a cursor."""
        self._require_owner_process()
        _positive(consumed_tokens, "consumed_tokens", 2**31 - 1)
        checkpoint, sequence = self.load(
            checkpoint_digest, expected_tokenizer_digest=expected_tokenizer_digest,
        )
        cursor = checkpoint.cursor + consumed_tokens
        if cursor > len(sequence.token_ids):
            raise LongContextSpoolError("advance exceeds remaining tokens")
        return self._publish_checkpoint(
            self._checkpoint(sequence, checkpoint.object_digest, cursor, checkpoint.digest)
        )


__all__ = ["LongContextSpool", "LongContextSpoolError", "SpoolCheckpoint", "read_selected_sequence"]
