"""Triple-replica admission checkpoints with bounded, fail-closed quorum recovery.

This is a local persistence/recovery building block, NOT a consensus protocol.
Every deployment must provide separate storage failure domains and single-writer
fencing. A trusted external witness must pin the latest committed digest or
monotonic sequence floor when rollback resistance is required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import hashlib
import hmac
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
AUTHENTICATED_REPLICA_SCHEMA = "skeleton.ai.authenticated-admission-replica.v1"


class _NewerAuthenticatedTerm(ModelRuntimeError):
    """Protect a signed future leadership term from an obsolete writer."""


class _AuthenticatedFork(ModelRuntimeError):
    """Protect conflicting lineage with the same signing leadership term."""


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
        if isinstance(replica, (FileCheckpointReplica, AuthenticatedFileCheckpointReplica)):
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
        except (_NewerAuthenticatedTerm, _AuthenticatedFork):
            # A validly authenticated higher term or same-term fork is not
            # accidental damage. Never silently overwrite that evidence.
            raise
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


def repair_redundant_checkpoint(
    replicas: Sequence[CheckpointReplica],
    *,
    expected_policy: RuntimePolicy | None = None,
    expected_limits: AdmissionLimits | None = None,
    minimum_sequence: int = 0,
    expected_digest: str | None = None,
) -> ReplicationReceipt:
    """Rebuild a degraded third copy from a quorum-validated revision.

    Refuses to repair without a two-copy quorum. Publish preflight also
    refuses overwriting any *valid* higher or conflicting revision. If a
    trusted independent commit witness is available, pass expected_digest
    and minimum_sequence; do not guess which revision should win.
    """
    recovered = recover_redundant_checkpoint(
        replicas,
        expected_policy=expected_policy,
        expected_limits=expected_limits,
        minimum_sequence=minimum_sequence,
        expected_digest=expected_digest,
    )
    return publish_redundant_checkpoint(
        recovered.scheduler,
        replicas,
        expected_policy=expected_policy,
        expected_limits=expected_limits,
        minimum_sequence=max(minimum_sequence, recovered.sequence),
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


def _authenticated_canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ModelRuntimeError("invalid authenticated checkpoint encoding") from exc


def _authenticated_digest(value: object) -> str:
    if (type(value) is not str or len(value) != 64 or
            any(char not in "0123456789abcdef" for char in value)):
        raise ModelRuntimeError("invalid authenticated checkpoint digest")
    return value


@dataclass(frozen=True, slots=True)
class AuthenticatedFileCheckpointReplica:
    """HMAC/term-gated adapter around the canonical FileCheckpointReplica.

    This is an adapter for the existing two-of-three publication and recovery
    methods, not a second quorum implementation. The caller must supply a
    securely loaded key and independently fenced term to *each* member.
    """

    name: str
    failure_domain: str
    path: Path
    leader_term: int
    secret_key: bytes = field(repr=False)
    expected_parent_digest: str | None = None

    def __post_init__(self) -> None:
        if type(self.leader_term) is not int or not 0 <= self.leader_term <= 2**63 - 1:
            raise ModelRuntimeError("invalid authenticated leadership term")
        if type(self.secret_key) is not bytes or not 32 <= len(self.secret_key) <= 4096:
            raise ModelRuntimeError("authenticated checkpoint key must be 32-4096 bytes")
        if self.expected_parent_digest is not None:
            _authenticated_digest(self.expected_parent_digest)
        FileCheckpointReplica(self.name, self.failure_domain, self.path)

    def _backend(self) -> FileCheckpointReplica:
        return FileCheckpointReplica(self.name, self.failure_domain, self.path)

    def _mac(self, unsigned: dict[str, object]) -> str:
        return hmac.new(
            self.secret_key, _authenticated_canonical(unsigned), hashlib.sha256,
        ).hexdigest()

    def read(self) -> dict[str, object] | None:
        envelope = self._backend().read()
        if envelope is None:
            return None
        keys = {
            "schema", "member", "leader_term", "parent_digest",
            "snapshot_digest", "snapshot", "mac",
        }
        if type(envelope) is not dict or set(envelope) != keys:
            raise ModelRuntimeError("invalid authenticated checkpoint fields")
        if (envelope["schema"] != AUTHENTICATED_REPLICA_SCHEMA or
                envelope["member"] != self.name):
            raise ModelRuntimeError("authenticated checkpoint member mismatch")
        signature = _authenticated_digest(envelope["mac"])
        unsigned = {key: value for key, value in envelope.items() if key != "mac"}
        if not hmac.compare_digest(signature, self._mac(unsigned)):
            raise ModelRuntimeError("authenticated checkpoint HMAC mismatch")
        term = envelope["leader_term"]
        if type(term) is not int or not 0 <= term <= 2**63 - 1:
            raise ModelRuntimeError("invalid authenticated checkpoint term")
        parent = envelope["parent_digest"]
        if parent is not None:
            _authenticated_digest(parent)
        if term > self.leader_term:
            raise _NewerAuthenticatedTerm("signed newer leadership term cannot be overwritten")
        if term < self.leader_term:
            raise ModelRuntimeError("authenticated checkpoint below trusted leadership term")
        if (self.expected_parent_digest is not None and
                parent != self.expected_parent_digest and
                envelope["snapshot_digest"] != self.expected_parent_digest):
            # During a new publication, the existing checkpoint is the
            # *predecessor* of the candidate and naturally has a different
            # parent. A same-term value is compatible only if it already
            # belongs to this lineage OR is the exact expected predecessor.
            raise _AuthenticatedFork("authenticated checkpoint parent revision conflict")
        snapshot = envelope["snapshot"]
        if type(snapshot) is not dict:
            raise ModelRuntimeError("invalid authenticated checkpoint snapshot")
        digest = _authenticated_digest(envelope["snapshot_digest"])
        if snapshot.get("digest") != digest:
            raise ModelRuntimeError("authenticated checkpoint snapshot digest mismatch")
        return copy.deepcopy(snapshot)

    def write(self, snapshot: dict[str, object]) -> None:
        # Reuse the canonical scheduler checkpoint validator. The publication
        # coordinator already verifies live state and readback against quorum.
        _validated(
            snapshot, expected_policy=None, expected_limits=None,
            minimum_sequence=0,
        )
        # Guard direct adapter callers as well as the quorum coordinator.
        # A surviving authenticated newer term, same-sequence equivocation,
        # or predecessor self-cycle must never be silently overwritten.
        try:
            old = self.read()
        except (_NewerAuthenticatedTerm, _AuthenticatedFork):
            raise
        except (ModelRuntimeError, OSError):
            old = None
        if old is not None:
            if old["sequence"] > snapshot["sequence"]:
                raise ModelRuntimeError("refusing authenticated checkpoint regression")
            if old["sequence"] == snapshot["sequence"] and old["digest"] != snapshot["digest"]:
                raise ModelRuntimeError("conflicting authenticated checkpoint at same sequence")
            if (self.expected_parent_digest == old["digest"] and
                    snapshot["sequence"] <= old["sequence"]):
                raise ModelRuntimeError("authenticated checkpoint must advance predecessor")
        unsigned = {
            "schema": AUTHENTICATED_REPLICA_SCHEMA,
            "member": self.name,
            "leader_term": self.leader_term,
            "parent_digest": self.expected_parent_digest,
            "snapshot_digest": snapshot["digest"],
            "snapshot": copy.deepcopy(snapshot),
        }
        self._backend().write({**unsigned, "mac": self._mac(unsigned)})


__all__ = [
    "AuthenticatedFileCheckpointReplica", "AUTHENTICATED_REPLICA_SCHEMA",
    "CheckpointReplica", "FileCheckpointReplica", "ReplicationReceipt",
    "RedundantRecovery", "publish_redundant_checkpoint",
    "recover_redundant_checkpoint", "repair_redundant_checkpoint",
    "REPLICA_COUNT", "REQUIRED_QUORUM",
    "MAX_CHECKPOINT_BYTES",
]
