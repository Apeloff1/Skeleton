"""Transactional repository mutation with bounded leases and rollback.

This module is intentionally stdlib-only and does not grant mutation authority by
itself. Callers must obtain a path-scoped lease, stage changes, and commit through
one transaction. Commit is optimistic: optional expected digests fence stale
writers, and partial filesystem failure restores every already-replaced path.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import tempfile
import threading
import time
from typing import Iterable


class RepositoryTransactionError(RuntimeError):
    """Base error for transactional repository mutation."""


class LeaseConflictError(RepositoryTransactionError):
    """Raised when a live lease overlaps requested mutation scope."""


class LeaseExpiredError(RepositoryTransactionError):
    """Raised when a transaction uses an expired or released lease."""


class StaleWriteError(RepositoryTransactionError):
    """Raised when optimistic file identity no longer matches."""


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise RepositoryTransactionError("path must be non-empty canonical POSIX text")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise RepositoryTransactionError(f"unsafe repository path: {value!r}")
    if pure.as_posix() != value:
        raise RepositoryTransactionError(f"non-canonical repository path: {value!r}")
    return value


def _overlap(left: str, right: str) -> bool:
    return (
        left == right
        or left.startswith(right.rstrip("/") + "/")
        or right.startswith(left.rstrip("/") + "/")
    )


@dataclass(frozen=True, slots=True)
class EditLease:
    lease_id: str
    owner_id: str
    paths: tuple[str, ...]
    acquired_at: float
    expires_at: float

    def live(self, now: float) -> bool:
        return now < self.expires_at


class LeaseRegistry:
    """In-memory bounded path lease registry.

    Durable automation can persist lease receipts externally; this class owns only
    collision semantics and live-process fencing.
    """

    def __init__(
        self,
        *,
        clock=time.time,
        max_leases: int = 256,
        max_ttl_s: float = 1800.0,
    ) -> None:
        if isinstance(max_leases, bool) or not isinstance(max_leases, int):
            raise TypeError("max_leases must be an integer")
        if (
            isinstance(max_ttl_s, bool)
            or not isinstance(max_ttl_s, (int, float))
            or not math.isfinite(float(max_ttl_s))
        ):
            raise TypeError("max_ttl_s must be finite numeric")
        if max_leases <= 0 or float(max_ttl_s) <= 0:
            raise ValueError("lease bounds must be positive")
        self._clock = clock
        self._max_leases = max_leases
        self._max_ttl_s = float(max_ttl_s)
        self._leases: dict[str, EditLease] = {}
        self._lock = threading.RLock()

    def _prune(self, now: float) -> None:
        expired = [key for key, lease in self._leases.items() if not lease.live(now)]
        for key in expired:
            self._leases.pop(key, None)

    def acquire(self, owner_id: str, paths: Iterable[str], *, ttl_s: float = 300.0) -> EditLease:
        owner = str(owner_id).strip()
        if not owner or len(owner) > 192:
            raise ValueError("owner_id must be non-empty bounded text")
        if (
            isinstance(ttl_s, bool)
            or not isinstance(ttl_s, (int, float))
            or not math.isfinite(float(ttl_s))
        ):
            raise TypeError("lease ttl must be finite numeric")
        ttl = float(ttl_s)
        if ttl <= 0 or ttl > self._max_ttl_s:
            raise ValueError("lease ttl exceeds policy")
        normalized = tuple(sorted({_normalize_path(path) for path in paths}))
        if not normalized:
            raise ValueError("lease requires at least one path")
        now = float(self._clock())
        with self._lock:
            self._prune(now)
            if len(self._leases) >= self._max_leases:
                raise LeaseConflictError("lease registry capacity exhausted")
            for lease in self._leases.values():
                if any(_overlap(left, right) for left in normalized for right in lease.paths):
                    raise LeaseConflictError(
                        f"requested mutation scope overlaps live lease {lease.lease_id}"
                    )
            lease = EditLease(
                lease_id=secrets.token_hex(16),
                owner_id=owner,
                paths=normalized,
                acquired_at=now,
                expires_at=now + ttl,
            )
            self._leases[lease.lease_id] = lease
            return lease

    def require(self, lease_id: str, owner_id: str) -> EditLease:
        now = float(self._clock())
        with self._lock:
            self._prune(now)
            lease = self._leases.get(str(lease_id))
            if lease is None or lease.owner_id != str(owner_id):
                raise LeaseExpiredError("edit lease is missing, expired, or owned by another actor")
            return lease

    @contextmanager
    def guard(self, lease_id: str, owner_id: str):
        """Hold lease-registry exclusivity for one commit critical section."""
        with self._lock:
            now = float(self._clock())
            self._prune(now)
            lease = self._leases.get(str(lease_id))
            if lease is None or lease.owner_id != str(owner_id):
                raise LeaseExpiredError(
                    "edit lease is missing, expired, or owned by another actor"
                )
            yield lease

    def release(self, lease_id: str, owner_id: str) -> bool:
        with self._lock:
            lease = self._leases.get(str(lease_id))
            if lease is None:
                return False
            if lease.owner_id != str(owner_id):
                raise LeaseExpiredError("cannot release another owner's lease")
            self._leases.pop(lease.lease_id, None)
            return True

    def snapshot(self) -> tuple[EditLease, ...]:
        now = float(self._clock())
        with self._lock:
            self._prune(now)
            return tuple(sorted(self._leases.values(), key=lambda item: item.lease_id))


@dataclass(frozen=True, slots=True)
class PatchEntry:
    path: str
    before_sha256: str | None
    after_sha256: str


@dataclass(frozen=True, slots=True)
class PatchReceipt:
    transaction_id: str
    lease_id: str
    owner_id: str
    entries: tuple[PatchEntry, ...]
    committed_at: float


class WorkspaceTransaction:
    """Path-fenced optimistic filesystem transaction."""

    def __init__(
        self,
        root: str | Path,
        registry: LeaseRegistry,
        lease: EditLease,
        *,
        clock=time.time,
    ) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise RepositoryTransactionError("repository root must be a directory")
        self.registry = registry
        canonical_lease = registry.require(lease.lease_id, lease.owner_id)
        if canonical_lease != lease:
            raise RepositoryTransactionError(
                "lease receipt does not match registry authority"
            )
        self.lease = canonical_lease
        self._clock = clock
        self.transaction_id = secrets.token_hex(16)
        self._staged: dict[str, tuple[bytes, str | None]] = {}
        self._closed = False

    def _target(self, relative: str) -> Path:
        rel = _normalize_path(relative)
        if not any(
            _overlap(rel, scope)
            and (rel == scope or rel.startswith(scope.rstrip("/") + "/"))
            for scope in self.lease.paths
        ):
            raise RepositoryTransactionError(f"path is outside lease scope: {rel}")

        # Inspect the unresolved repository-relative path first. Calling
        # Path.resolve() before this check would follow an existing final
        # symlink and make the explicit target-symlink guard ineffective.
        candidate = self.root / rel
        cursor = self.root
        for part in PurePosixPath(rel).parts[:-1]:
            cursor = cursor / part
            if cursor.is_symlink():
                raise RepositoryTransactionError(
                    "mutation parent must not be a symlink"
                )
        if candidate.is_symlink():
            raise RepositoryTransactionError(
                "mutation target must not be a symlink"
            )

        path = candidate.resolve(strict=False)
        if not path.is_relative_to(self.root):
            raise RepositoryTransactionError("mutation path escapes repository root")
        return path

    def stage_bytes(
        self,
        relative: str,
        data: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> None:
        if self._closed:
            raise RepositoryTransactionError("transaction is closed")
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("staged data must be bytes")
        rel = _normalize_path(relative)
        self._target(rel)
        if expected_sha256 is not None:
            if len(expected_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha256):
                raise ValueError("expected_sha256 must be lowercase SHA-256")
        self._staged[rel] = (bytes(data), expected_sha256)

    def stage_text(
        self,
        relative: str,
        text: str,
        *,
        expected_sha256: str | None = None,
    ) -> None:
        if not isinstance(text, str):
            raise TypeError("staged text must be str")
        self.stage_bytes(relative, text.encode("utf-8"), expected_sha256=expected_sha256)

    def rollback(self) -> None:
        self._staged.clear()
        self._closed = True

    def commit(self) -> PatchReceipt:
        if self._closed:
            raise RepositoryTransactionError("transaction is closed")
        if not self._staged:
            raise RepositoryTransactionError("transaction has no staged changes")
        # Hold the registry lock throughout commit so release/reacquire cannot
        # interleave an overlapping writer between optimistic preflight and
        # atomic replacements.
        with self.registry.guard(self.lease.lease_id, self.lease.owner_id):
            return self._commit_guarded()

    def _commit_guarded(self) -> PatchReceipt:
        temp_root = Path(tempfile.mkdtemp(prefix=".repo-txn-", dir=self.root))
        backups: dict[str, Path | None] = {}
        replaced: list[str] = []
        entries: list[PatchEntry] = []
        try:
            # Preflight every path before changing any target.
            prepared: dict[str, Path] = {}
            for rel, (data, expected) in sorted(self._staged.items()):
                target = self._target(rel)
                before: str | None = None
                if target.exists():
                    if not target.is_file():
                        raise RepositoryTransactionError(f"target is not a regular file: {rel}")
                    before = _digest_bytes(target.read_bytes())
                if expected is not None and before != expected:
                    raise StaleWriteError(
                        f"optimistic identity mismatch for {rel}: expected {expected}, got {before}"
                    )
                staged = temp_root / "staged" / rel
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(data)
                prepared[rel] = staged
                entries.append(PatchEntry(rel, before, _digest_bytes(data)))

            # Make recoverable backups, then atomically replace one file at a time.
            for rel, staged in sorted(prepared.items()):
                self.registry.require(self.lease.lease_id, self.lease.owner_id)
                target = self._target(rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    backup = temp_root / "backup" / rel
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                    backups[rel] = backup
                else:
                    backups[rel] = None
                os.replace(staged, target)
                replaced.append(rel)

            self.registry.require(self.lease.lease_id, self.lease.owner_id)
            receipt = PatchReceipt(
                transaction_id=self.transaction_id,
                lease_id=self.lease.lease_id,
                owner_id=self.lease.owner_id,
                entries=tuple(entries),
                committed_at=float(self._clock()),
            )
            self._closed = True
            self._staged.clear()
            return receipt
        except Exception:
            for rel in reversed(replaced):
                target = self._target(rel)
                backup = backups.get(rel)
                if backup is None:
                    try:
                        target.unlink()
                    except FileNotFoundError:
                        pass
                elif backup.exists():
                    os.replace(backup, target)
            raise
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


__all__ = [
    "EditLease",
    "LeaseConflictError",
    "LeaseExpiredError",
    "LeaseRegistry",
    "PatchEntry",
    "PatchReceipt",
    "RepositoryTransactionError",
    "StaleWriteError",
    "WorkspaceTransaction",
]
