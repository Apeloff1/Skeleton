"""Triple-replica admission checkpoints with bounded, fail-closed quorum recovery.

This is a local persistence/recovery building block, NOT a consensus protocol.
Every deployment must provide separate storage failure domains and single-writer
fencing. A trusted external witness must pin the latest committed digest or
monotonic sequence floor when rollback resistance is required.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Protocol, Sequence, runtime_checkable

from .admission_checkpoint import restore_admission_scheduler
from .admission_scheduler import AdmissionLimits, RuntimeAdmissionScheduler
from .flgb_model_runtime import ModelRuntimeError
from .runtime_policy import RuntimePolicy


REPLICA_COUNT = 3
REQUIRED_QUORUM = 2
MAX_CHECKPOINT_BYTES = 128 * 1024 * 1024


@runtime_checkable
class CheckpointReplica(Protocol):
    """Independent backing store supplied by the operator.

    `name` and `failure_domain` are identifiers, not independently
    attested claims. Adapters must provide read-after-write consistency.
    """

    name: str
    failure_domain: str

    def read(self) -> dict[str, object] | None:
        """Read an isolated snapshot, or None for an empty slot."""

    def write(self, snapshot: dict[str, object]) -> None:
        """Atomically replace this replica's snapshot where supported."""


def _slots(replicas: Sequence[CheckpointReplica]) -> tuple[CheckpointReplica, ...]:
    try:
        slots = tuple(replicas)
    except (TypeError, ValueError) as exc:
        raise ModelRuntimeError("invalid checkpoint replica collection") from exc
    if len(slots) != REPLICA_COUNT:
        raise ModelRuntimeError("exactly three checkpoint replicas required")
    names: set[str] = set()
    domains: set[str] = set()
    identities: set[int] = set()
    file_paths: set[Path] = set()
    for replica in slots:
        if not isinstance(replica, CheckpointReplica):
            raise ModelRuntimeError("invalid checkpoint replica adapter")
        name, domain = replica.name, replica.failure_domain
        for value in (name, domain):
            if type(value) is not str or not 1 <= len(value) <= 128:
                raise ModelRuntimeError("invalid checkpoint replica identity")
        if name in names or domain in domains or id(replica) in identities:
            raise ModelRuntimeError("duplicate checkpoint replica failure domain")
        names.add(name)
        domains.add(domain)
        identities.add(id(replica))
        if isinstance(replica, FileCheckpointReplica):
            path = replica.path.resolve(strict=False)
            if path in file_paths:
                raise ModelRuntimeError("duplicate checkpoint storage path")
            file_paths.add(path)
    return slots


@dataclass(frozen=True, slots=True)
class ReplicationReceipt:
    digest: str
    sequence: int
    acknowledged: tuple[str, ...]
    unavailable: tuple[str, ...]
    degraded: bool


@dataclass(frozen=True, slots=True)
class RedundantRecovery:
    scheduler: RuntimeAdmissionScheduler
    digest: str
    sequence: int
    matching: tuple[str, ...]
    rejected: tuple[str, ...]
    degraded: bool


def _decode_snapshot(snapshot: object) -> tuple[int, str] | None:
    if type(snapshot) is not dict:
        return None
    sequence = snapshot.get("sequence")
    digest = snapshot.get("digest")
    if type(sequence) is not int or sequence < 0:
        return None
    if type(digest) is not str or len(digest) != 64:
        return None
    return sequence, digest


def _validated(
    value: object, *,
    expected_policy: RuntimePolicy | None,
    expected_limits: AdmissionLimits | None,
    minimum_sequence: int,
    expected_digest: str | None = None,
) -> RuntimeAdmissionScheduler:
    return restore_admission_scheduler(
        value,
        expected_policy=expected_policy,
        expected_limits=expected_limits,
        minimum_sequence=minimum_sequence,
        expected_digest=expected_digest,
    )


def publish_redundant_checkpoint(
    scheduler: RuntimeAdmissionScheduler,
    replicas: Sequence[CheckpointReplica],
    *,
    expected_policy: RuntimePolicy | None = None,
    expected_limits: AdmissionLimits | None = None,
    minimum_sequence: int = 0,
) -> ReplicationReceipt:
    """Replicate a canonical snapshot to three independently owned slots.

    Preflight rejects a newer or conflicting revision before any write.
    Read-back parity is required for every counted acknowledgement. A quorum
    receipt is not a distributed transaction, fsync attestation or permission
    to run multiple concurrent writers.
    """
    slots = _slots(replicas)
    if not isinstance(scheduler, RuntimeAdmissionScheduler):
        raise ModelRuntimeError("RuntimeAdmissionScheduler required")
    snapshot = scheduler.snapshot()
    _validated(
        snapshot, expected_policy=expected_policy,
        expected_limits=expected_limits, minimum_sequence=minimum_sequence,
    )
    sequence = snapshot["sequence"]
    digest = snapshot["digest"]

    # Check for competing/newer valid writers before mutating any slot.
    for replica in slots:
        try:
            previous = replica.read()
            if previous is None:
                continue
            _validated(
                previous, expected_policy=expected_policy,
                expected_limits=expected_limits, minimum_sequence=0,
            )
        except Exception:
            # Corrupt and unreachable copies are replaceable, provided at
            # least two other replicas acknowledge the candidate.
            continue
        prior = _decode_snapshot(previous)
        if prior is None:
            continue
        old_sequence, old_digest = prior
        if old_sequence > sequence:
            raise ModelRuntimeError("refusing stale checkpoint overwrite")
        if old_sequence == sequence and old_digest != digest:
            raise ModelRuntimeError("conflicting checkpoint at same sequence")

    acknowledged: list[str] = []
    unavailable: list[str] = []
    for replica in slots:
        try:
            replica.write(copy.deepcopy(snapshot))
            readback = replica.read()
            if readback != snapshot:
                raise ModelRuntimeError("checkpoint replica readback mismatch")
            _validated(
                readback, expected_policy=expected_policy,
                expected_limits=expected_limits, minimum_sequence=sequence,
                expected_digest=digest,
            )
        except Exception:
            unavailable.append(replica.name)
        else:
            acknowledged.append(replica.name)
    if len(acknowledged) < REQUIRED_QUORUM:
        raise ModelRuntimeError("checkpoint publication lacks two-replica quorum")
    return ReplicationReceipt(
        digest, sequence, tuple(acknowledged), tuple(unavailable),
        len(acknowledged) != REPLICA_COUNT,
    )


def recover_redundant_checkpoint(
    replicas: Sequence[CheckpointReplica],
    *,
    expected_policy: RuntimePolicy | None = None,
    expected_limits: AdmissionLimits | None = None,
    minimum_sequence: int = 0,
    expected_digest: str | None = None,
) -> RedundantRecovery:
    """Select a quorum-agreed *valid* revision; never trust one healthy slot.

    A lone newer snapshot may be a partially completed write, so an older
    matching quorum may be selected. Trusted independent sequence/digest pins
    are therefore essential when callers need rollback protection.
    """
    slots = _slots(replicas)
    if type(minimum_sequence) is not int or minimum_sequence < 0:
        raise ModelRuntimeError("invalid checkpoint recovery sequence floor")
    if expected_digest is not None and (
        type(expected_digest) is not str or len(expected_digest) != 64
        or any(ch not in "0123456789abcdef" for ch in expected_digest)
    ):
        raise ModelRuntimeError("invalid expected recovery checkpoint digest")

    cohorts: dict[tuple[int, str], list[str]] = {}
    payloads: dict[tuple[int, str], dict[str, object]] = {}
    rejected: list[str] = []
    for replica in slots:
        try:
            record = replica.read()
            if record is None:
                raise ModelRuntimeError("checkpoint replica empty")
            _validated(
                record, expected_policy=expected_policy,
                expected_limits=expected_limits, minimum_sequence=minimum_sequence,
                expected_digest=expected_digest,
            )
            key = _decode_snapshot(record)
            if key is None:
                raise ModelRuntimeError("invalid checkpoint identity")
        except Exception:
            rejected.append(replica.name)
            continue
        cohorts.setdefault(key, []).append(replica.name)
        payloads.setdefault(key, record)
    qualified = [
        (key, names) for key, names in cohorts.items()
        if len(names) >= REQUIRED_QUORUM
    ]
    if len(qualified) != 1:
        raise ModelRuntimeError("checkpoint recovery lacks unique two-replica quorum")
    (sequence, digest), names = qualified[0]
    scheduler = _validated(
        payloads[(sequence, digest)],
        expected_policy=expected_policy,
        expected_limits=expected_limits,
        minimum_sequence=minimum_sequence,
        expected_digest=expected_digest,
    )
    return RedundantRecovery(
        scheduler, digest, sequence,
        tuple(names),
        tuple(replica.name for replica in slots if replica.name not in names),
        len(names) != REPLICA_COUNT,
    )


def _no_duplicate_keys(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ModelRuntimeError("duplicate JSON checkpoint key")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class FileCheckpointReplica:
    """Atomic JSON checkpoint in a pre-created, operator-managed directory.

    Use distinct *real* storage fault domains for the three instances. Merely
    naming directories differently does not create hardware redundancy.
    """

    name: str
    failure_domain: str
    path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path) or not self.path.name:
            raise ModelRuntimeError("checkpoint path must be a file Path")

    def read(self) -> dict[str, object] | None:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CHECKPOINT_BYTES:
                raise ModelRuntimeError("unsafe or oversized checkpoint storage file")
            content = stream.read(MAX_CHECKPOINT_BYTES + 1)
            if len(content) > MAX_CHECKPOINT_BYTES:
                raise ModelRuntimeError("checkpoint storage byte budget exceeded")
        try:
            parsed = json.loads(
                content.decode("utf-8", errors="strict"),
                object_pairs_hook=_no_duplicate_keys,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ModelRuntimeError("nonfinite JSON checkpoint value")
                ),
            )
        except (ValueError, UnicodeError, TypeError) as exc:
            raise ModelRuntimeError("checkpoint storage is not valid JSON") from exc
        if type(parsed) is not dict:
            raise ModelRuntimeError("checkpoint storage root must be an object")
        return parsed

    def write(self, snapshot: dict[str, object]) -> None:
        data = json.dumps(
            snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", errors="strict")
        if len(data) > MAX_CHECKPOINT_BYTES:
            raise ModelRuntimeError("checkpoint storage byte budget exceeded")
        # Parents are preprovisioned by the caller; no unrequested directories
        # or symlink targets are created by this adapter.
        parent = self.path.parent
        if not parent.is_dir() or parent.is_symlink():
            raise ModelRuntimeError("checkpoint storage parent is not provisioned")
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=parent, prefix=".checkpoint-", delete=False,
            ) as handle:
                temporary = handle.name
                os.chmod(temporary, 0o600)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
            # POSIX directory sync protects the rename after sudden power
            # failure; unsupported platforms require storage-level durability.
            if os.name == "posix":
                dir_fd = os.open(parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass


__all__ = [
    "CheckpointReplica", "FileCheckpointReplica", "ReplicationReceipt",
    "RedundantRecovery", "publish_redundant_checkpoint",
    "recover_redundant_checkpoint", "REPLICA_COUNT", "REQUIRED_QUORUM",
    "MAX_CHECKPOINT_BYTES",
]
