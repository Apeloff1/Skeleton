"""Atomic, separately rooted on-disk replicas for admission checkpoints.

Each member has a precreated, configured directory. Durable writes use a
same-directory temporary file, fsync and os.replace followed by directory fsync.
No cross-process distributed lease or CAS is implied: only an externally
fenced *single writer* may save/repair a set of replicas concurrently.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import tempfile
from threading import RLock
from typing import Mapping

from .admission_replicas import (
    MAX_REPLICA_BYTES, QuorumAdmissionRecovery, _key, _member, _integer,
    _seal, decode_admission_replica, recover_admission_quorum,
)
from .admission_checkpoint import restore_admission_scheduler
from .admission_scheduler import RuntimeAdmissionScheduler
from .flgb_model_runtime import ModelRuntimeError


_FILENAME = "admission-checkpoint.json"


@dataclass(frozen=True, slots=True)
class ReplicaPublicationReceipt:
    leader_term: int
    sequence: int
    snapshot_digest: str
    committed_members: tuple[str, ...]
    failed_members: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReplicaReadSet:
    copies: dict[str, bytes | None]
    io_failures: tuple[str, ...]


class AdmissionReplicaFileStore:
    """Independent storage slots with bounded, verified, atomic local writes.

    Directories must be provisioned on independent failure domains by the
    operator. Merely using distinct paths on one disk is not high availability.
    """

    def __init__(self, directories: Mapping[str, str | Path]) -> None:
        if not isinstance(directories, Mapping) or len(directories) not in (3, 5, 7):
            raise ModelRuntimeError("three, five or seven replica directories required")
        roots: dict[str, Path] = {}
        for member, folder in directories.items():
            _member(member)
            if type(folder) not in (str, Path):
                raise ModelRuntimeError("invalid replica directory")
            candidate = Path(folder)
            if candidate.is_symlink() or not candidate.is_dir():
                raise ModelRuntimeError("replica directory must exist and not be a symlink")
            root = candidate.resolve(strict=True)
            if root in roots.values():
                raise ModelRuntimeError("replica directories must be distinct")
            roots[member] = root
        self._roots = roots
        self.members = tuple(sorted(roots))
        self._lock = RLock()

    def _path(self, member_id: str) -> Path:
        _member(member_id)
        try:
            return self._roots[member_id] / _FILENAME
        except KeyError as exc:
            raise ModelRuntimeError("unconfigured replica member") from exc

    def read(self, member_id: str) -> bytes | None:
        """Read a regular file without following a symlink or allocating unbounded data."""
        target = self._path(member_id)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with self._lock:
            try:
                fd = os.open(target, flags)
            except FileNotFoundError:
                return None
            try:
                status = os.fstat(fd)
                if not stat.S_ISREG(status.st_mode):
                    raise ModelRuntimeError("replica source is not a regular file")
                if not 0 < status.st_size <= MAX_REPLICA_BYTES:
                    raise ModelRuntimeError("replica file outside bounded size")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    payload = stream.read(MAX_REPLICA_BYTES + 1)
                if len(payload) != status.st_size:
                    raise ModelRuntimeError("replica file changed during read")
                return payload
            finally:
                os.close(fd)

    def scan(self) -> ReplicaReadSet:
        """Continue past one damaged/unreadable member, recording its identity."""
        copies: dict[str, bytes | None] = {}
        failed: list[str] = []
        with self._lock:
            for member in self.members:
                try:
                    copies[member] = self.read(member)
                except (OSError, ModelRuntimeError):
                    copies[member] = None
                    failed.append(member)
        return ReplicaReadSet(copies, tuple(failed))

    def _atomic_replace(self, member_id: str, blob: bytes) -> None:
        target = self._path(member_id)
        if target.is_symlink():
            raise ModelRuntimeError("refusing to replace replica symlink")
        fd, temporary = tempfile.mkstemp(prefix=".admission-replica-", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
            # The target's directory is fixed at constructor time; a
            # same-filesystem os.replace provides atomic visibility.
            os.replace(temporary, target)
            temporary = ""
            if hasattr(os, "O_DIRECTORY"):
                dir_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def save(
        self, member_id: str, blob: bytes, *, secret_key: bytes,
        minimum_term: int, minimum_sequence: int,
    ) -> None:
        """Write only verified nonregressing state; never overwrite corrupt evidence."""
        _key(secret_key)
        _integer(minimum_term, "minimum term")
        _integer(minimum_sequence, "minimum sequence")
        current = decode_admission_replica(
            blob, member_id=member_id, secret_key=secret_key,
            minimum_term=minimum_term, minimum_sequence=minimum_sequence,
        )
        with self._lock:
            existing = self.read(member_id)
            if existing is not None:
                old = decode_admission_replica(
                    existing, member_id=member_id, secret_key=secret_key
                )
                if (current.leader_term < old.leader_term or
                        current.sequence < old.sequence):
                    raise ModelRuntimeError("replica checkpoint regression refused")
                if (current.leader_term == old.leader_term and
                        current.sequence == old.sequence and
                        current.vote != old.vote):
                    raise ModelRuntimeError("conflicting replica checkpoint revision")
                if existing == blob:
                    return
            self._atomic_replace(member_id, blob)

    def repair(
        self, member_id: str, recovered: QuorumAdmissionRecovery, *,
        secret_key: bytes, minimum_term: int, minimum_sequence: int,
    ) -> None:
        """Repair only an explicitly degraded member from a validated quorum.

        The caller must hold the independent leader lease, and pass its trusted
        durable term/sequence floor. This function does not grant such authority.
        """
        _key(secret_key)
        if not isinstance(recovered, QuorumAdmissionRecovery):
            raise ModelRuntimeError("validated quorum recovery required")
        if member_id not in recovered.repair_targets:
            raise ModelRuntimeError("replica member is not a quorum repair target")
        if (recovered.leader_term < _integer(minimum_term, "minimum term") or
                recovered.sequence < _integer(minimum_sequence, "minimum sequence")):
            raise ModelRuntimeError("quorum repair below trusted monotonic floor")
        blob = recovered.rebuild_replica(member_id, secret_key=secret_key)
        decode_admission_replica(
            blob, member_id=member_id, secret_key=secret_key,
            minimum_term=minimum_term, minimum_sequence=minimum_sequence,
            expected_digest=recovered.snapshot_digest,
        )
        with self._lock:
            # An existing authenticated newer revision is evidence, not a
            # corrupt cache entry; never destroy it during read repair.
            try:
                old = self.read(member_id)
            except (OSError, ModelRuntimeError):
                old = None
            if old is not None:
                try:
                    existing = decode_admission_replica(
                        old, member_id=member_id, secret_key=secret_key,
                    )
                except ModelRuntimeError:
                    existing = None
                if existing is not None:
                    if (existing.leader_term > recovered.leader_term or
                            existing.sequence > recovered.sequence):
                        raise ModelRuntimeError("refusing to repair over newer replica")
                    if (existing.leader_term == recovered.leader_term and
                            existing.sequence == recovered.sequence and
                            existing.vote != (
                                recovered.leader_term, recovered.sequence,
                                recovered.parent_digest, recovered.snapshot_digest,
                            )):
                        raise ModelRuntimeError("conflicting replica revision needs operator intervention")
            # A damaged target is overwritten only after an explicit repair
            # operation backed by quorum; no automatic read-repair on scan().
            self._atomic_replace(member_id, blob)

    def publish(
        self, scheduler: RuntimeAdmissionScheduler, *, leader_term: int,
        secret_key: bytes, minimum_term: int, minimum_sequence: int,
        parent_digest: str | None = None,
    ) -> ReplicaPublicationReceipt:
        """Seal one immutable state, publish, and independently recheck quorum.

        Partial failure is not silently acknowledged as committed. A required
        trusted external leadership lease must fence other processes.
        """
        if not isinstance(scheduler, RuntimeAdmissionScheduler):
            raise ModelRuntimeError("RuntimeAdmissionScheduler required")
        secret_key = _key(secret_key)
        term = _integer(leader_term, "leadership term")
        floor_term = _integer(minimum_term, "minimum term")
        floor_seq = _integer(minimum_sequence, "minimum sequence")
        if term < floor_term:
            raise ModelRuntimeError("publication below trusted leadership term")
        snapshot = scheduler.snapshot()
        restore_admission_scheduler(
            snapshot, expected_policy=scheduler.policy,
            expected_limits=scheduler.limits,
            minimum_sequence=floor_seq, expected_digest=snapshot["digest"],
        )
        sequence = snapshot["sequence"]
        committed: list[str] = []
        failed: list[str] = []
        # Publication uses a fixed snapshot even if the caller later changes
        # its live scheduler. Never build independent replica states in a loop.
        for member in self.members:
            blob = _seal(
                snapshot, member_id=member, leader_term=term,
                parent_digest=parent_digest, secret_key=secret_key,
            )
            try:
                self.save(
                    member, blob, secret_key=secret_key,
                    minimum_term=floor_term, minimum_sequence=floor_seq,
                )
                committed.append(member)
            except (OSError, ModelRuntimeError):
                failed.append(member)
        # Read-after-write proves the *surviving* copies actually comprise a
        # signed majority for this exact snapshot, not merely two write calls.
        try:
            recovered = recover_admission_quorum(
                self.scan().copies, members=self.members, secret_key=secret_key,
                minimum_term=term, minimum_sequence=sequence,
                expected_policy=scheduler.policy,
                expected_limits=scheduler.limits,
                expected_digest=snapshot["digest"],
            )
        except ModelRuntimeError as exc:
            raise ModelRuntimeError(
                "replicated publication failed to establish a durable quorum"
            ) from exc
        if recovered.parent_digest != parent_digest:
            raise ModelRuntimeError("replicated publication parent revision mismatch")
        return ReplicaPublicationReceipt(
            term, sequence, snapshot["digest"],
            recovered.supporters, tuple(sorted(set(self.members) - set(recovered.supporters))),
        )


__all__ = [
    "ReplicaReadSet", "ReplicaPublicationReceipt", "AdmissionReplicaFileStore",
]
