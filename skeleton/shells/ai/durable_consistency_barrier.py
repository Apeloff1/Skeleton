"""Signed stabilized cross-chain consistency barriers.

A durable evidence deployment has several independently committed chains:
decision journals, execution receipts, audit evidence, and other append-only
authority logs. Backup or failover needs a coherent observed cut across those
chains. This module captures such a cut by repeatedly reading and verifying
every member until the complete member vector is unchanged across multiple
passes.

Important semantics:

* A barrier is a stabilized observational cut, not a transactional snapshot.
* It does not stop writers and grants no execution, pruning, or restore authority.
* Every member binds the exact head and hot-floor/archive state observed.
* Publication is signed and generation-monotonic per barrier name.
* A later verifier can require each captured root to remain a committed ancestor
  even after chains continue to grow.

True atomic multi-store snapshots require writer coordination outside this
module. The explicit atomic_snapshot=False field prevents consumers from
mistaking stabilization for atomicity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Iterable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_hot_floor import HotFloorPosition
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


GENESIS_HASH = "0" * 64


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


def _timestamp(name: str, value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{name} must be finite and non-negative")
    return float(value)


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


class DurableConsistencyBarrierState(str, Enum):
    STABLE = "stable"
    UNSTABLE = "unstable"
    INVALID = "invalid"


@dataclass(frozen=True)
class DurableConsistencyBarrierPolicy:
    max_chains: int = 32
    stabilization_passes: int = 2
    max_capture_attempts: int = 8
    require_chain_verify: bool = True
    require_hot_floor_consistency: bool = True
    require_nonempty: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_chains",
            "stabilization_passes",
            "max_capture_attempts",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive integer")
        if self.stabilization_passes < 2:
            raise ValueError(
                "stabilization_passes must be at least two"
            )
        for name in (
            "require_chain_verify",
            "require_hot_floor_consistency",
            "require_nonempty",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")

    @property
    def digest(self) -> str:
        return _stable_digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "max_chains": self.max_chains,
            "stabilization_passes": self.stabilization_passes,
            "max_capture_attempts": self.max_capture_attempts,
            "require_chain_verify": self.require_chain_verify,
            "require_hot_floor_consistency": (
                self.require_hot_floor_consistency
            ),
            "require_nonempty": self.require_nonempty,
        }


@dataclass(frozen=True)
class DurableConsistencyBarrierMember:
    chain_id: str
    head_sequence: int
    head_root: str
    hot_floor_sequence: int
    hot_floor_root: str
    hot_floor_id: str
    hot_floor_archive_id: str
    hot_floor_archive_manifest_digest: str
    hot_floor_fencing_token: int
    hot_length: int
    chain_verified: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=128,
            ),
        )
        object.__setattr__(
            self,
            "head_root",
            _digest("head_root", self.head_root),
        )
        object.__setattr__(
            self,
            "hot_floor_root",
            _digest("hot_floor_root", self.hot_floor_root),
        )
        object.__setattr__(
            self,
            "hot_floor_id",
            _digest(
                "hot_floor_id",
                self.hot_floor_id,
                optional=True,
            ),
        )
        if self.hot_floor_archive_id:
            _identity(
                "hot_floor_archive_id",
                self.hot_floor_archive_id,
                maximum=256,
            )
        object.__setattr__(
            self,
            "hot_floor_archive_manifest_digest",
            _digest(
                "hot_floor_archive_manifest_digest",
                self.hot_floor_archive_manifest_digest,
                optional=True,
            ),
        )
        for name in (
            "head_sequence",
            "hot_floor_sequence",
            "hot_floor_fencing_token",
            "hot_length",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if self.hot_floor_sequence > self.head_sequence:
            raise ValueError(
                "hot floor may not be ahead of chain head"
            )
        if (
            self.head_sequence == 0
            and self.head_root != GENESIS_HASH
        ):
            raise ValueError(
                "empty chain head must use genesis root"
            )
        if (
            self.head_sequence > 0
            and self.head_root == GENESIS_HASH
        ):
            raise ValueError(
                "non-empty chain may not use genesis head"
            )
        if self.hot_floor_sequence == 0:
            if self.hot_floor_root != GENESIS_HASH:
                raise ValueError(
                    "genesis hot floor must use genesis root"
                )
            if (
                self.hot_floor_id
                or self.hot_floor_archive_id
                or self.hot_floor_archive_manifest_digest
                or self.hot_floor_fencing_token
            ):
                raise ValueError(
                    "genesis hot floor may not carry archive authority"
                )
        else:
            if self.hot_floor_root == GENESIS_HASH:
                raise ValueError(
                    "non-genesis hot floor may not use genesis root"
                )
            if not self.hot_floor_id:
                raise ValueError(
                    "non-genesis hot floor requires floor_id"
                )
            if not self.hot_floor_archive_id:
                raise ValueError(
                    "non-genesis hot floor requires archive_id"
                )
            if not self.hot_floor_archive_manifest_digest:
                raise ValueError(
                    "non-genesis hot floor requires archive manifest"
                )
            if self.hot_floor_fencing_token <= 0:
                raise ValueError(
                    "non-genesis hot floor requires fencing token"
                )
        if not isinstance(self.chain_verified, bool):
            raise ValueError("chain_verified must be bool")
        expected_hot_length = (
            self.head_sequence - self.hot_floor_sequence
            if self.hot_floor_sequence > 0
            else self.head_sequence
        )
        if self.hot_length != expected_hot_length:
            raise ValueError(
                "hot_length does not match head/floor positions"
            )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(include_digest=False)
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "head_sequence": self.head_sequence,
            "head_root": self.head_root,
            "hot_floor_sequence": self.hot_floor_sequence,
            "hot_floor_root": self.hot_floor_root,
            "hot_floor_id": self.hot_floor_id,
            "hot_floor_archive_id": self.hot_floor_archive_id,
            "hot_floor_archive_manifest_digest": (
                self.hot_floor_archive_manifest_digest
            ),
            "hot_floor_fencing_token": (
                self.hot_floor_fencing_token
            ),
            "hot_length": self.hot_length,
            "chain_verified": self.chain_verified,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableConsistencyBarrier:
    schema_version: int
    barrier_id: str
    barrier_name: str
    generation: int
    previous_barrier_id: str
    previous_barrier_digest: str
    operator_id: str
    captured_at: float
    policy_digest: str
    stabilization_passes: int
    capture_attempt: int
    members: tuple[DurableConsistencyBarrierMember, ...]
    atomic_snapshot: bool = False
    write_fenced: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported consistency barrier schema"
            )
        object.__setattr__(
            self,
            "barrier_id",
            _digest("barrier_id", self.barrier_id),
        )
        object.__setattr__(
            self,
            "barrier_name",
            _identity(
                "barrier_name",
                self.barrier_name,
                maximum=256,
            ),
        )
        for name in (
            "previous_barrier_id",
            "previous_barrier_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                    optional=True,
                ),
            )
        _identity(
            "operator_id",
            self.operator_id,
            maximum=256,
        )
        object.__setattr__(
            self,
            "captured_at",
            _timestamp("captured_at", self.captured_at),
        )
        object.__setattr__(
            self,
            "policy_digest",
            _digest("policy_digest", self.policy_digest),
        )
        for name in (
            "generation",
            "stabilization_passes",
            "capture_attempt",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive integer"
                )
        if self.generation == 1:
            if (
                self.previous_barrier_id
                or self.previous_barrier_digest
            ):
                raise ValueError(
                    "first barrier generation may not bind predecessor"
                )
        else:
            if (
                not self.previous_barrier_id
                or not self.previous_barrier_digest
            ):
                raise ValueError(
                    "later barrier generation requires predecessor"
                )
        members = tuple(self.members)
        if not members:
            raise ValueError(
                "consistency barrier requires members"
            )
        chain_ids = tuple(
            item.chain_id
            for item in members
        )
        if chain_ids != tuple(sorted(chain_ids)):
            raise ValueError(
                "barrier members must be sorted by chain_id"
            )
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError(
                "barrier member chain_ids must be unique"
            )
        object.__setattr__(self, "members", members)
        if self.atomic_snapshot:
            raise ValueError(
                "consistency barrier may not claim atomic snapshot semantics"
            )
        if self.write_fenced:
            raise ValueError(
                "consistency barrier may not claim writer fencing"
            )
        expected = self.derive_id(
            barrier_name=self.barrier_name,
            generation=self.generation,
            previous_barrier_id=self.previous_barrier_id,
            previous_barrier_digest=(
                self.previous_barrier_digest
            ),
            operator_id=self.operator_id,
            captured_at=self.captured_at,
            policy_digest=self.policy_digest,
            stabilization_passes=self.stabilization_passes,
            capture_attempt=self.capture_attempt,
            members=members,
        )
        if expected != self.barrier_id:
            raise ValueError(
                "barrier_id does not match barrier content"
            )

    @staticmethod
    def derive_id(
        *,
        barrier_name: str,
        generation: int,
        previous_barrier_id: str,
        previous_barrier_digest: str,
        operator_id: str,
        captured_at: float,
        policy_digest: str,
        stabilization_passes: int,
        capture_attempt: int,
        members: Iterable[
            DurableConsistencyBarrierMember
        ],
    ) -> str:
        raw = json.dumps(
            {
                "barrier_name": barrier_name,
                "generation": generation,
                "previous_barrier_id": previous_barrier_id,
                "previous_barrier_digest": (
                    previous_barrier_digest
                ),
                "operator_id": operator_id,
                "captured_at": float(captured_at),
                "policy_digest": policy_digest,
                "stabilization_passes": stabilization_passes,
                "capture_attempt": capture_attempt,
                "members": [
                    item.digest for item in members
                ],
                "atomic_snapshot": False,
                "write_fenced": False,
                "authority": "durable-consistency-barrier",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.unsigned_dict()
        )

    @property
    def member_digest(self) -> str:
        return _stable_digest(
            [item.digest for item in self.members]
        )

    def member(
        self,
        chain_id: str,
    ) -> DurableConsistencyBarrierMember:
        for item in self.members:
            if item.chain_id == chain_id:
                return item
        raise KeyError(chain_id)

    def unsigned_dict(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "barrier_id": self.barrier_id,
            "barrier_name": self.barrier_name,
            "generation": self.generation,
            "previous_barrier_id": self.previous_barrier_id,
            "previous_barrier_digest": (
                self.previous_barrier_digest
            ),
            "operator_id": self.operator_id,
            "captured_at": self.captured_at,
            "policy_digest": self.policy_digest,
            "stabilization_passes": self.stabilization_passes,
            "capture_attempt": self.capture_attempt,
            "members": [
                item.to_dict() for item in self.members
            ],
            "member_digest": self.member_digest,
            "atomic_snapshot": False,
            "write_fenced": False,
            "grants_execution_authority": False,
            "grants_pruning_authority": False,
            "grants_restore_authority": False,
        }

    def to_dict(self) -> dict[str, object]:
        data = self.unsigned_dict()
        data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class SignedDurableConsistencyBarrier:
    barrier: DurableConsistencyBarrier
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.barrier,
            DurableConsistencyBarrier,
        ):
            raise TypeError(
                "barrier must be DurableConsistencyBarrier"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )
        if (
            self.signature.artifact_type
            != "ai-durable-consistency-barrier"
        ):
            raise ValueError(
                "invalid consistency barrier artifact type"
            )
        if (
            self.signature.artifact_digest
            != self.barrier.digest
        ):
            raise ValueError(
                "consistency barrier signed digest mismatch"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "barrier": self.barrier.to_dict(),
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class DurableConsistencyBarrierHead:
    barrier_name: str
    generation: int
    barrier_id: str
    barrier_digest: str

    def __post_init__(self) -> None:
        _identity(
            "barrier_name",
            self.barrier_name,
            maximum=256,
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError(
                "barrier head generation must be positive"
            )
        object.__setattr__(
            self,
            "barrier_id",
            _digest("barrier_id", self.barrier_id),
        )
        object.__setattr__(
            self,
            "barrier_digest",
            _digest("barrier_digest", self.barrier_digest),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "barrier_name": self.barrier_name,
            "generation": self.generation,
            "barrier_id": self.barrier_id,
            "barrier_digest": self.barrier_digest,
        }


@dataclass(frozen=True)
class StoredDurableConsistencyBarrier:
    revision: int
    signed: SignedDurableConsistencyBarrier

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "barrier revision must be positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "signed": self.signed.to_dict(),
        }


@dataclass(frozen=True)
class DurableConsistencyBarrierPublication:
    stored: StoredDurableConsistencyBarrier
    head_revision: int
    head: DurableConsistencyBarrierHead
    head_created: bool
    capture_attempts: int
    stabilization_passes: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.head_revision, bool)
            or not isinstance(self.head_revision, int)
            or self.head_revision <= 0
        ):
            raise ValueError(
                "barrier publication head_revision must be positive"
            )
        for name in (
            "capture_attempts",
            "stabilization_passes",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive integer"
                )
        if (
            self.stored.signed.barrier.barrier_id
            != self.head.barrier_id
            or self.stored.signed.barrier.digest
            != self.head.barrier_digest
        ):
            raise ValueError(
                "barrier publication head does not match stored barrier"
            )
        if not isinstance(self.head_created, bool):
            raise ValueError(
                "head_created must be bool"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "head_revision": self.head_revision,
            "head": self.head.to_dict(),
            "head_created": self.head_created,
            "capture_attempts": self.capture_attempts,
            "stabilization_passes": (
                self.stabilization_passes
            ),
        }


class DurableConsistencyBarrierConflict(RuntimeError):
    pass


class DurableConsistencyBarrierCorruption(RuntimeError):
    pass


class DurableConsistencyBarrierUnstable(RuntimeError):
    pass


class DurableConsistencyBarrierStore:
    """Immutable signed barriers and monotonic heads per logical barrier."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-durable-consistency-barrier",
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid consistency barrier namespace"
            )
        if not isinstance(signer, ArtifactSigner):
            raise TypeError("signer must be ArtifactSigner")
        self.backend = backend
        self.signer = signer
        self.namespace = namespace

    @staticmethod
    def _record_key(
        barrier_id: str,
    ) -> str:
        barrier_id = _digest(
            "barrier_id",
            barrier_id,
        )
        return "barrier:" + barrier_id

    @staticmethod
    def _head_key(
        barrier_name: str,
    ) -> str:
        barrier_name = _identity(
            "barrier_name",
            barrier_name,
            maximum=256,
        )
        return "head:" + hashlib.sha256(
            barrier_name.encode()
        ).hexdigest()

    def _verify_signature(
        self,
        item: SignedDurableConsistencyBarrier,
    ) -> None:
        try:
            self.signer.verify(item.signature)
        except ArtifactSignatureError as exc:
            raise DurableConsistencyBarrierCorruption(
                "consistency barrier signature verification failed"
            ) from exc
        if (
            item.signature.artifact_digest
            != item.barrier.digest
        ):
            raise DurableConsistencyBarrierCorruption(
                "consistency barrier signature digest mismatch"
            )

    def get(
        self,
        barrier_id: str,
    ) -> StoredDurableConsistencyBarrier | None:
        record = self.backend.get(
            self.namespace,
            self._record_key(barrier_id),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            SignedDurableConsistencyBarrier,
        ):
            raise DurableConsistencyBarrierCorruption(
                "consistency barrier backend value type mismatch"
            )
        self._verify_signature(record.value)
        if (
            record.value.barrier.barrier_id
            != barrier_id
        ):
            raise DurableConsistencyBarrierCorruption(
                "consistency barrier record/key mismatch"
            )
        return StoredDurableConsistencyBarrier(
            record.revision,
            record.value,
        )

    def head(
        self,
        barrier_name: str,
    ) -> tuple[
        int,
        DurableConsistencyBarrierHead,
    ] | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(barrier_name),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableConsistencyBarrierHead,
        ):
            raise DurableConsistencyBarrierCorruption(
                "consistency barrier head value type mismatch"
            )
        if (
            record.value.barrier_name
            != barrier_name
        ):
            raise DurableConsistencyBarrierCorruption(
                "consistency barrier head/key mismatch"
            )
        return record.revision, record.value

    def current(
        self,
        barrier_name: str,
    ) -> StoredDurableConsistencyBarrier | None:
        head = self.head(barrier_name)
        if head is None:
            return None
        _, value = head
        stored = self.get(value.barrier_id)
        if stored is None:
            raise DurableConsistencyBarrierCorruption(
                "barrier head references missing record"
            )
        if (
            stored.signed.barrier.digest
            != value.barrier_digest
            or stored.signed.barrier.generation
            != value.generation
        ):
            raise DurableConsistencyBarrierCorruption(
                "barrier head does not match record"
            )
        return stored

    def publish(
        self,
        barrier: DurableConsistencyBarrier,
    ) -> DurableConsistencyBarrierPublication:
        if not isinstance(
            barrier,
            DurableConsistencyBarrier,
        ):
            raise TypeError(
                "barrier must be DurableConsistencyBarrier"
            )
        current_head = self.head(
            barrier.barrier_name
        )
        if current_head is None:
            expected_generation = 1
            expected_previous_id = ""
            expected_previous_digest = ""
        else:
            _, head = current_head
            expected_generation = head.generation + 1
            expected_previous_id = head.barrier_id
            expected_previous_digest = (
                head.barrier_digest
            )
        if barrier.generation != expected_generation:
            raise DurableConsistencyBarrierConflict(
                "barrier generation is stale or skipped"
            )
        if (
            barrier.previous_barrier_id
            != expected_previous_id
            or barrier.previous_barrier_digest
            != expected_previous_digest
        ):
            raise DurableConsistencyBarrierConflict(
                "barrier predecessor binding differs from current head"
            )

        signature = self.signer.sign(
            "ai-durable-consistency-barrier",
            barrier.digest,
            metadata={
                "barrier_name": barrier.barrier_name,
                "generation": str(barrier.generation),
            },
        )
        signed = SignedDurableConsistencyBarrier(
            barrier,
            signature,
        )
        key = self._record_key(
            barrier.barrier_id
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                stored_record = self.backend.put_if_absent(
                    self.namespace,
                    key,
                    signed,
                )
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
                stored_record = existing
        else:
            stored_record = existing
        if not isinstance(
            stored_record.value,
            SignedDurableConsistencyBarrier,
        ):
            raise DurableConsistencyBarrierCorruption(
                "barrier record has invalid type"
            )
        self._verify_signature(
            stored_record.value
        )
        if stored_record.value.barrier != barrier:
            raise DurableConsistencyBarrierConflict(
                "barrier_id already binds different content"
            )

        new_head = DurableConsistencyBarrierHead(
            barrier.barrier_name,
            barrier.generation,
            barrier.barrier_id,
            barrier.digest,
        )
        head_key = self._head_key(
            barrier.barrier_name
        )
        current_record = self.backend.get(
            self.namespace,
            head_key,
        )
        head_created = current_record is None
        if current_record is None:
            try:
                head_record = self.backend.put_if_absent(
                    self.namespace,
                    head_key,
                    new_head,
                )
            except DistributedStateConflict:
                current_record = self.backend.get(
                    self.namespace,
                    head_key,
                )
                if current_record is None:
                    raise
                head_record = current_record
                head_created = False
        else:
            if not isinstance(
                current_record.value,
                DurableConsistencyBarrierHead,
            ):
                raise DurableConsistencyBarrierCorruption(
                    "barrier head has invalid type"
                )
            if (
                current_record.value.generation
                != barrier.generation - 1
                or current_record.value.barrier_id
                != barrier.previous_barrier_id
                or current_record.value.barrier_digest
                != barrier.previous_barrier_digest
            ):
                raise DurableConsistencyBarrierConflict(
                    "barrier head changed during publication"
                )
            try:
                head_record = self.backend.compare_and_swap(
                    self.namespace,
                    head_key,
                    expected_revision=(
                        current_record.revision
                    ),
                    value=new_head,
                )
            except DistributedStateConflict as exc:
                raise DurableConsistencyBarrierConflict(
                    "barrier head CAS lost to concurrent publisher"
                ) from exc

        if not isinstance(
            head_record.value,
            DurableConsistencyBarrierHead,
        ):
            raise DurableConsistencyBarrierCorruption(
                "published barrier head has invalid type"
            )
        if head_record.value != new_head:
            raise DurableConsistencyBarrierConflict(
                "published barrier head differs from requested barrier"
            )
        return DurableConsistencyBarrierPublication(
            StoredDurableConsistencyBarrier(
                stored_record.revision,
                stored_record.value,
            ),
            head_record.revision,
            head_record.value,
            head_created,
            barrier.capture_attempt,
            barrier.stabilization_passes,
        )

    def require(
        self,
        barrier_id: str,
    ) -> StoredDurableConsistencyBarrier:
        stored = self.get(barrier_id)
        if stored is None:
            raise DurableConsistencyBarrierConflict(
                "required consistency barrier is missing"
            )
        self._verify_signature(
            stored.signed
        )
        return stored


class DurableConsistencyBarrierCoordinator:
    """Capture stabilized verified member vectors and publish signed barriers."""

    def __init__(
        self,
        store: DurableConsistencyBarrierStore,
        *,
        policy: DurableConsistencyBarrierPolicy
        | None = None,
        clock: Callable[[], float] = time.time,
        between_passes: Callable[
            [int, int], None
        ] | None = None,
    ) -> None:
        if not isinstance(
            store,
            DurableConsistencyBarrierStore,
        ):
            raise TypeError(
                "store must be DurableConsistencyBarrierStore"
            )
        self.store = store
        self.policy = (
            policy
            or DurableConsistencyBarrierPolicy()
        )
        if not isinstance(
            self.policy,
            DurableConsistencyBarrierPolicy,
        ):
            raise TypeError(
                "policy must be DurableConsistencyBarrierPolicy"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        if (
            between_passes is not None
            and not callable(between_passes)
        ):
            raise TypeError(
                "between_passes must be callable"
            )
        self._clock = clock
        self._between_passes = between_passes

    def _entries(
        self,
        chains: Iterable[
            tuple[str, object]
        ],
    ) -> tuple[tuple[str, object], ...]:
        entries = tuple(chains)
        if (
            self.policy.require_nonempty
            and not entries
        ):
            raise ValueError(
                "consistency barrier requires at least one chain"
            )
        if len(entries) > self.policy.max_chains:
            raise DurableConsistencyBarrierConflict(
                "consistency barrier chain bound exceeded"
            )
        normalized: list[
            tuple[str, object]
        ] = []
        seen: set[str] = set()
        for item in entries:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
            ):
                raise ValueError(
                    "barrier chains must be (chain_id, chain) pairs"
                )
            chain_id, chain = item
            chain_id = _identity(
                "chain_id",
                chain_id,
                maximum=128,
            )
            if chain_id in seen:
                raise ValueError(
                    "duplicate consistency barrier chain_id"
                )
            seen.add(chain_id)
            for method in (
                "head",
                "verify",
                "root_hash",
                "length",
            ):
                if not callable(
                    getattr(chain, method, None)
                ):
                    raise TypeError(
                        f"chain {chain_id} does not implement {method}"
                    )
            normalized.append(
                (chain_id, chain)
            )
        return tuple(
            sorted(
                normalized,
                key=lambda item: item[0],
            )
        )

    @staticmethod
    def _floor(
        chain: object,
    ) -> HotFloorPosition:
        method = getattr(
            chain,
            "hot_floor",
            None,
        )
        if not callable(method):
            return HotFloorPosition.genesis()
        floor = method()
        if isinstance(
            floor,
            HotFloorPosition,
        ):
            return floor

        # Core receipt chains deliberately expose a tiny dependency-neutral
        # genesis position instead of importing the AI durability layer.  That
        # adapter is safe only at genesis: it carries no archive authority and
        # therefore cannot smuggle an unsigned non-genesis floor into a signed
        # consistency barrier.  Normalize that one shape while keeping every
        # active floor type-strict and fail-closed.
        try:
            sequence = floor.sequence
            root_hash = floor.root_hash
        except Exception as exc:
            raise DurableConsistencyBarrierCorruption(
                "chain hot_floor returned invalid type"
            ) from exc
        if (
            type(sequence) is int
            and sequence == 0
            and root_hash == GENESIS_HASH
        ):
            return HotFloorPosition.genesis()
        raise DurableConsistencyBarrierCorruption(
            "chain hot_floor returned invalid type"
        )

    def _observe(
        self,
        chain_id: str,
        chain: object,
    ) -> DurableConsistencyBarrierMember:
        head = chain.head()
        try:
            sequence = int(head.sequence)
            root = str(head.root_hash)
        except Exception as exc:
            raise DurableConsistencyBarrierCorruption(
                f"chain {chain_id} head has invalid shape"
            ) from exc
        if sequence < 0:
            raise DurableConsistencyBarrierCorruption(
                f"chain {chain_id} head sequence is negative"
            )
        root = _digest(
            "head_root",
            root,
        )
        verified = bool(
            chain.verify()
        )
        if (
            self.policy.require_chain_verify
            and not verified
        ):
            raise DurableConsistencyBarrierCorruption(
                f"chain {chain_id} failed integrity verification"
            )
        floor = self._floor(chain)
        if floor.sequence > sequence:
            raise DurableConsistencyBarrierCorruption(
                f"chain {chain_id} hot floor is ahead of head"
            )
        if (
            self.policy.require_hot_floor_consistency
            and floor.sequence > 0
        ):
            if (
                not floor.floor_id
                or not floor.archive_id
                or not floor.archive_manifest_digest
                or floor.fencing_token <= 0
            ):
                raise DurableConsistencyBarrierCorruption(
                    f"chain {chain_id} hot floor lacks signed archive bindings"
                )
        hot_length_method = getattr(
            chain,
            "hot_length",
            None,
        )
        if callable(hot_length_method):
            hot_length = int(
                hot_length_method()
            )
        else:
            hot_length = (
                sequence - floor.sequence
                if floor.sequence > 0
                else sequence
            )
        return DurableConsistencyBarrierMember(
            chain_id,
            sequence,
            root,
            floor.sequence,
            floor.root_hash,
            floor.floor_id,
            floor.archive_id,
            floor.archive_manifest_digest,
            floor.fencing_token,
            hot_length,
            verified,
        )

    def _vector(
        self,
        entries: tuple[
            tuple[str, object],
            ...,
        ],
    ) -> tuple[
        DurableConsistencyBarrierMember,
        ...,
    ]:
        return tuple(
            self._observe(
                chain_id,
                chain,
            )
            for chain_id, chain
            in entries
        )

    def capture(
        self,
        barrier_name: str,
        chains: Iterable[
            tuple[str, object]
        ],
        *,
        operator_id: str,
    ) -> DurableConsistencyBarrierPublication:
        barrier_name = _identity(
            "barrier_name",
            barrier_name,
            maximum=256,
        )
        operator_id = _identity(
            "operator_id",
            operator_id,
            maximum=256,
        )
        entries = self._entries(chains)

        stable: tuple[
            DurableConsistencyBarrierMember,
            ...,
        ] | None = None
        used_attempt = 0
        for attempt in range(
            1,
            self.policy.max_capture_attempts + 1,
        ):
            used_attempt = attempt
            first = self._vector(entries)
            stable_attempt = True
            previous = first
            for pass_index in range(
                2,
                self.policy.stabilization_passes + 1,
            ):
                if self._between_passes is not None:
                    self._between_passes(
                        attempt,
                        pass_index,
                    )
                current = self._vector(entries)
                if current != previous:
                    stable_attempt = False
                    break
                previous = current
            if stable_attempt:
                stable = first
                break
        if stable is None:
            raise DurableConsistencyBarrierUnstable(
                "cross-chain heads did not stabilize within capture bound"
            )

        current = self.store.current(
            barrier_name
        )
        if current is None:
            generation = 1
            previous_id = ""
            previous_digest = ""
        else:
            prior = current.signed.barrier
            generation = prior.generation + 1
            previous_id = prior.barrier_id
            previous_digest = prior.digest

        captured_at = _timestamp(
            "captured_at",
            self._clock(),
        )
        barrier_id = DurableConsistencyBarrier.derive_id(
            barrier_name=barrier_name,
            generation=generation,
            previous_barrier_id=previous_id,
            previous_barrier_digest=(
                previous_digest
            ),
            operator_id=operator_id,
            captured_at=captured_at,
            policy_digest=self.policy.digest,
            stabilization_passes=(
                self.policy.stabilization_passes
            ),
            capture_attempt=used_attempt,
            members=stable,
        )
        barrier = DurableConsistencyBarrier(
            1,
            barrier_id,
            barrier_name,
            generation,
            previous_id,
            previous_digest,
            operator_id,
            captured_at,
            self.policy.digest,
            self.policy.stabilization_passes,
            used_attempt,
            stable,
            False,
            False,
        )
        return self.store.publish(
            barrier
        )

    def inspect_current(
        self,
        barrier_name: str,
        chains: Iterable[
            tuple[str, object]
        ],
    ) -> DurableConsistencyBarrierState:
        stored = self.store.current(
            barrier_name
        )
        if stored is None:
            return DurableConsistencyBarrierState.INVALID
        entries = self._entries(chains)
        by_id = {
            item.chain_id: item
            for item in stored.signed.barrier.members
        }
        if set(by_id) != {
            chain_id
            for chain_id, _ in entries
        }:
            return DurableConsistencyBarrierState.INVALID
        for chain_id, chain in entries:
            expected = by_id[chain_id]
            current = self._observe(
                chain_id,
                chain,
            )
            if (
                current.head_sequence
                < expected.head_sequence
            ):
                return DurableConsistencyBarrierState.INVALID
            if (
                current.head_sequence
                == expected.head_sequence
                and current.head_root
                != expected.head_root
            ):
                return DurableConsistencyBarrierState.INVALID
            if (
                current.hot_floor_sequence
                > expected.head_sequence
            ):
                return DurableConsistencyBarrierState.UNSTABLE
            if current.head_root != expected.head_root:
                ancestor = getattr(
                    chain,
                    "root_is_ancestor",
                    None,
                )
                if (
                    not callable(ancestor)
                    or not bool(
                        ancestor(
                            expected.head_root
                        )
                    )
                ):
                    return DurableConsistencyBarrierState.INVALID
        return DurableConsistencyBarrierState.STABLE
