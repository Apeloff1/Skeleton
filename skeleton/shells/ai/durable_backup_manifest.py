"""Signed disaster-recovery manifests built from consistency barriers.

A backup manifest binds one signed consistency barrier to the exact hot suffix
that must be copied for every member chain.  If a chain was already compacted
at barrier capture time, the manifest also binds the archive identity and
archive manifest digest carried by the signed hot floor.

The manifest is evidence describing a backup set. It does not copy bytes and
does not authorize restore, pruning, or execution. Segment contents remain in
existing chain/archive storage. A backup implementation can export those
objects separately and use this manifest as the integrity contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import math
import time
from typing import Callable, Iterable, Mapping

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_consistency_barrier import (
    DurableConsistencyBarrier,
    DurableConsistencyBarrierMember,
    DurableConsistencyBarrierStore,
)
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


def _canonical_item(item: object) -> object:
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if is_dataclass(item):
        return asdict(item)
    if isinstance(item, Mapping):
        return dict(item)
    raise TypeError(
        "backup segment items must provide to_dict or be dataclasses/mappings"
    )


@dataclass(frozen=True)
class DurableBackupManifestPolicy:
    max_chains: int = 32
    max_segment_items: int = 100_000
    require_chain_verify: bool = True
    require_barrier_root_ancestor: bool = True
    require_archive_for_compacted_prefix: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_chains",
            "max_segment_items",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive integer")
        for name in (
            "require_chain_verify",
            "require_barrier_root_ancestor",
            "require_archive_for_compacted_prefix",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")

    @property
    def digest(self) -> str:
        return _stable_digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "max_chains": self.max_chains,
            "max_segment_items": self.max_segment_items,
            "require_chain_verify": self.require_chain_verify,
            "require_barrier_root_ancestor": (
                self.require_barrier_root_ancestor
            ),
            "require_archive_for_compacted_prefix": (
                self.require_archive_for_compacted_prefix
            ),
        }


@dataclass(frozen=True)
class DurableBackupChainManifest:
    chain_id: str
    barrier_member_digest: str
    barrier_head_sequence: int
    barrier_head_root: str
    prefix_archive_required: bool
    prefix_archive_id: str
    prefix_archive_manifest_digest: str
    segment_start_sequence: int
    segment_start_root: str
    segment_end_sequence: int
    segment_end_root: str
    segment_item_count: int
    segment_digest: str
    serialization: str = "canonical-json-v1"

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
        for name in (
            "barrier_member_digest",
            "barrier_head_root",
            "segment_start_root",
            "segment_end_root",
            "segment_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        if self.prefix_archive_id:
            _identity(
                "prefix_archive_id",
                self.prefix_archive_id,
                maximum=256,
            )
        object.__setattr__(
            self,
            "prefix_archive_manifest_digest",
            _digest(
                "prefix_archive_manifest_digest",
                self.prefix_archive_manifest_digest,
                optional=True,
            ),
        )
        for name in (
            "barrier_head_sequence",
            "segment_start_sequence",
            "segment_end_sequence",
            "segment_item_count",
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
        if not isinstance(
            self.prefix_archive_required,
            bool,
        ):
            raise ValueError(
                "prefix_archive_required must be bool"
            )
        if (
            self.segment_end_sequence
            != self.barrier_head_sequence
            or self.segment_end_root
            != self.barrier_head_root
        ):
            raise ValueError(
                "backup segment end must equal barrier head"
            )
        if (
            self.segment_start_sequence
            > self.segment_end_sequence
        ):
            raise ValueError(
                "backup segment start may not exceed end"
            )
        expected_count = (
            self.segment_end_sequence
            - self.segment_start_sequence
        )
        if self.segment_item_count != expected_count:
            raise ValueError(
                "segment_item_count does not match sequence interval"
            )
        if self.segment_start_sequence == 0:
            if self.segment_start_root != GENESIS_HASH:
                raise ValueError(
                    "genesis segment start must use genesis root"
                )
            if (
                self.prefix_archive_required
                or self.prefix_archive_id
                or self.prefix_archive_manifest_digest
            ):
                raise ValueError(
                    "genesis backup prefix may not require archive"
                )
        else:
            if self.segment_start_root == GENESIS_HASH:
                raise ValueError(
                    "non-genesis segment start may not use genesis root"
                )
            if self.prefix_archive_required and (
                not self.prefix_archive_id
                or not self.prefix_archive_manifest_digest
            ):
                raise ValueError(
                    "compacted backup prefix requires archive authority"
                )
        if self.serialization != "canonical-json-v1":
            raise ValueError(
                "unsupported backup serialization"
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
            "barrier_member_digest": (
                self.barrier_member_digest
            ),
            "barrier_head_sequence": (
                self.barrier_head_sequence
            ),
            "barrier_head_root": self.barrier_head_root,
            "prefix_archive_required": (
                self.prefix_archive_required
            ),
            "prefix_archive_id": self.prefix_archive_id,
            "prefix_archive_manifest_digest": (
                self.prefix_archive_manifest_digest
            ),
            "segment_start_sequence": (
                self.segment_start_sequence
            ),
            "segment_start_root": (
                self.segment_start_root
            ),
            "segment_end_sequence": (
                self.segment_end_sequence
            ),
            "segment_end_root": self.segment_end_root,
            "segment_item_count": (
                self.segment_item_count
            ),
            "segment_digest": self.segment_digest,
            "serialization": self.serialization,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableBackupManifest:
    schema_version: int
    manifest_id: str
    backup_name: str
    generation: int
    previous_manifest_id: str
    previous_manifest_digest: str
    barrier_id: str
    barrier_digest: str
    barrier_name: str
    barrier_generation: int
    operator_id: str
    created_at: float
    policy_digest: str
    chains: tuple[DurableBackupChainManifest, ...]
    atomic_snapshot: bool = False
    restore_authorized: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable backup manifest schema"
            )
        object.__setattr__(
            self,
            "manifest_id",
            _digest("manifest_id", self.manifest_id),
        )
        object.__setattr__(
            self,
            "backup_name",
            _identity(
                "backup_name",
                self.backup_name,
                maximum=256,
            ),
        )
        for name in (
            "previous_manifest_id",
            "previous_manifest_digest",
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
        for name in (
            "barrier_id",
            "barrier_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        _identity(
            "barrier_name",
            self.barrier_name,
            maximum=256,
        )
        _identity(
            "operator_id",
            self.operator_id,
            maximum=256,
        )
        object.__setattr__(
            self,
            "created_at",
            _timestamp("created_at", self.created_at),
        )
        for name in (
            "generation",
            "barrier_generation",
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
                self.previous_manifest_id
                or self.previous_manifest_digest
            ):
                raise ValueError(
                    "first backup generation may not bind predecessor"
                )
        else:
            if (
                not self.previous_manifest_id
                or not self.previous_manifest_digest
            ):
                raise ValueError(
                    "later backup generation requires predecessor"
                )
        chains = tuple(self.chains)
        if not chains:
            raise ValueError(
                "backup manifest requires at least one chain"
            )
        chain_ids = tuple(
            item.chain_id for item in chains
        )
        if chain_ids != tuple(sorted(chain_ids)):
            raise ValueError(
                "backup chains must be sorted by chain_id"
            )
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError(
                "backup chain_ids must be unique"
            )
        object.__setattr__(self, "chains", chains)
        if self.atomic_snapshot:
            raise ValueError(
                "backup manifest may not claim atomic snapshot"
            )
        if self.restore_authorized:
            raise ValueError(
                "backup manifest may not authorize restore"
            )
        expected = self.derive_id(
            backup_name=self.backup_name,
            generation=self.generation,
            previous_manifest_id=(
                self.previous_manifest_id
            ),
            previous_manifest_digest=(
                self.previous_manifest_digest
            ),
            barrier_id=self.barrier_id,
            barrier_digest=self.barrier_digest,
            barrier_name=self.barrier_name,
            barrier_generation=(
                self.barrier_generation
            ),
            operator_id=self.operator_id,
            created_at=self.created_at,
            policy_digest=self.policy_digest,
            chains=chains,
        )
        if expected != self.manifest_id:
            raise ValueError(
                "manifest_id does not match backup content"
            )

    @staticmethod
    def derive_id(
        *,
        backup_name: str,
        generation: int,
        previous_manifest_id: str,
        previous_manifest_digest: str,
        barrier_id: str,
        barrier_digest: str,
        barrier_name: str,
        barrier_generation: int,
        operator_id: str,
        created_at: float,
        policy_digest: str,
        chains: Iterable[
            DurableBackupChainManifest
        ],
    ) -> str:
        raw = json.dumps(
            {
                "backup_name": backup_name,
                "generation": generation,
                "previous_manifest_id": (
                    previous_manifest_id
                ),
                "previous_manifest_digest": (
                    previous_manifest_digest
                ),
                "barrier_id": barrier_id,
                "barrier_digest": barrier_digest,
                "barrier_name": barrier_name,
                "barrier_generation": (
                    barrier_generation
                ),
                "operator_id": operator_id,
                "created_at": float(created_at),
                "policy_digest": policy_digest,
                "chains": [
                    item.digest for item in chains
                ],
                "atomic_snapshot": False,
                "restore_authorized": False,
                "authority": (
                    "durable-backup-manifest"
                ),
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
    def chain_digest(self) -> str:
        return _stable_digest(
            [item.digest for item in self.chains]
        )

    def chain(
        self,
        chain_id: str,
    ) -> DurableBackupChainManifest:
        for item in self.chains:
            if item.chain_id == chain_id:
                return item
        raise KeyError(chain_id)

    def unsigned_dict(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "backup_name": self.backup_name,
            "generation": self.generation,
            "previous_manifest_id": (
                self.previous_manifest_id
            ),
            "previous_manifest_digest": (
                self.previous_manifest_digest
            ),
            "barrier_id": self.barrier_id,
            "barrier_digest": self.barrier_digest,
            "barrier_name": self.barrier_name,
            "barrier_generation": (
                self.barrier_generation
            ),
            "operator_id": self.operator_id,
            "created_at": self.created_at,
            "policy_digest": self.policy_digest,
            "chains": [
                item.to_dict() for item in self.chains
            ],
            "chain_digest": self.chain_digest,
            "atomic_snapshot": False,
            "restore_authorized": False,
            "grants_execution_authority": False,
            "grants_pruning_authority": False,
        }

    def to_dict(self) -> dict[str, object]:
        data = self.unsigned_dict()
        data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class SignedDurableBackupManifest:
    manifest: DurableBackupManifest
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.manifest,
            DurableBackupManifest,
        ):
            raise TypeError(
                "manifest must be DurableBackupManifest"
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
            != "ai-durable-backup-manifest"
        ):
            raise ValueError(
                "invalid durable backup artifact type"
            )
        if (
            self.signature.artifact_digest
            != self.manifest.digest
        ):
            raise ValueError(
                "durable backup signed digest mismatch"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.to_dict(),
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class DurableBackupManifestHead:
    backup_name: str
    generation: int
    manifest_id: str
    manifest_digest: str

    def __post_init__(self) -> None:
        _identity(
            "backup_name",
            self.backup_name,
            maximum=256,
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError(
                "backup head generation must be positive"
            )
        object.__setattr__(
            self,
            "manifest_id",
            _digest(
                "manifest_id",
                self.manifest_id,
            ),
        )
        object.__setattr__(
            self,
            "manifest_digest",
            _digest(
                "manifest_digest",
                self.manifest_digest,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "backup_name": self.backup_name,
            "generation": self.generation,
            "manifest_id": self.manifest_id,
            "manifest_digest": (
                self.manifest_digest
            ),
        }


@dataclass(frozen=True)
class StoredDurableBackupManifest:
    revision: int
    signed: SignedDurableBackupManifest

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "backup manifest revision must be positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "signed": self.signed.to_dict(),
        }


@dataclass(frozen=True)
class DurableBackupManifestPublication:
    stored: StoredDurableBackupManifest
    head_revision: int
    head: DurableBackupManifestHead
    head_created: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.head_revision, bool)
            or not isinstance(self.head_revision, int)
            or self.head_revision <= 0
        ):
            raise ValueError(
                "backup publication head_revision must be positive"
            )
        if (
            self.stored.signed.manifest.manifest_id
            != self.head.manifest_id
            or self.stored.signed.manifest.digest
            != self.head.manifest_digest
        ):
            raise ValueError(
                "backup publication head mismatch"
            )
        if not isinstance(
            self.head_created,
            bool,
        ):
            raise ValueError(
                "head_created must be bool"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "head_revision": self.head_revision,
            "head": self.head.to_dict(),
            "head_created": self.head_created,
        }


class DurableBackupManifestConflict(RuntimeError):
    pass


class DurableBackupManifestCorruption(RuntimeError):
    pass


class DurableBackupManifestStore:
    """Immutable signed backup manifests plus monotonic named heads."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-durable-backup-manifest",
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid durable backup namespace"
            )
        if not isinstance(signer, ArtifactSigner):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        self.backend = backend
        self.signer = signer
        self.namespace = namespace

    @staticmethod
    def _record_key(
        manifest_id: str,
    ) -> str:
        return "manifest:" + _digest(
            "manifest_id",
            manifest_id,
        )

    @staticmethod
    def _head_key(
        backup_name: str,
    ) -> str:
        backup_name = _identity(
            "backup_name",
            backup_name,
            maximum=256,
        )
        return "head:" + hashlib.sha256(
            backup_name.encode()
        ).hexdigest()

    def _verify_signature(
        self,
        item: SignedDurableBackupManifest,
    ) -> None:
        try:
            self.signer.verify(
                item.signature
            )
        except ArtifactSignatureError as exc:
            raise DurableBackupManifestCorruption(
                "backup manifest signature verification failed"
            ) from exc
        if (
            item.signature.artifact_digest
            != item.manifest.digest
        ):
            raise DurableBackupManifestCorruption(
                "backup manifest signature digest mismatch"
            )

    def get(
        self,
        manifest_id: str,
    ) -> StoredDurableBackupManifest | None:
        record = self.backend.get(
            self.namespace,
            self._record_key(manifest_id),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            SignedDurableBackupManifest,
        ):
            raise DurableBackupManifestCorruption(
                "backup manifest backend value type mismatch"
            )
        self._verify_signature(
            record.value
        )
        if (
            record.value.manifest.manifest_id
            != manifest_id
        ):
            raise DurableBackupManifestCorruption(
                "backup manifest record/key mismatch"
            )
        return StoredDurableBackupManifest(
            record.revision,
            record.value,
        )

    def head(
        self,
        backup_name: str,
    ) -> tuple[
        int,
        DurableBackupManifestHead,
    ] | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(backup_name),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableBackupManifestHead,
        ):
            raise DurableBackupManifestCorruption(
                "backup manifest head type mismatch"
            )
        if (
            record.value.backup_name
            != backup_name
        ):
            raise DurableBackupManifestCorruption(
                "backup manifest head/key mismatch"
            )
        return record.revision, record.value

    def current(
        self,
        backup_name: str,
    ) -> StoredDurableBackupManifest | None:
        head = self.head(backup_name)
        if head is None:
            return None
        _, item = head
        stored = self.get(
            item.manifest_id
        )
        if stored is None:
            raise DurableBackupManifestCorruption(
                "backup head references missing manifest"
            )
        if (
            stored.signed.manifest.digest
            != item.manifest_digest
            or stored.signed.manifest.generation
            != item.generation
        ):
            raise DurableBackupManifestCorruption(
                "backup head does not match manifest"
            )
        return stored

    def publish(
        self,
        manifest: DurableBackupManifest,
    ) -> DurableBackupManifestPublication:
        if not isinstance(
            manifest,
            DurableBackupManifest,
        ):
            raise TypeError(
                "manifest must be DurableBackupManifest"
            )
        current = self.head(
            manifest.backup_name
        )
        if current is None:
            expected_generation = 1
            previous_id = ""
            previous_digest = ""
        else:
            _, head = current
            expected_generation = (
                head.generation + 1
            )
            previous_id = head.manifest_id
            previous_digest = (
                head.manifest_digest
            )
        if (
            manifest.generation
            != expected_generation
        ):
            raise DurableBackupManifestConflict(
                "backup manifest generation is stale or skipped"
            )
        if (
            manifest.previous_manifest_id
            != previous_id
            or manifest.previous_manifest_digest
            != previous_digest
        ):
            raise DurableBackupManifestConflict(
                "backup manifest predecessor differs from current head"
            )

        signature = self.signer.sign(
            "ai-durable-backup-manifest",
            manifest.digest,
            metadata={
                "backup_name": (
                    manifest.backup_name
                ),
                "generation": str(
                    manifest.generation
                ),
                "barrier_id": (
                    manifest.barrier_id
                ),
            },
        )
        signed = SignedDurableBackupManifest(
            manifest,
            signature,
        )
        key = self._record_key(
            manifest.manifest_id
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
            SignedDurableBackupManifest,
        ):
            raise DurableBackupManifestCorruption(
                "backup record has invalid type"
            )
        self._verify_signature(
            stored_record.value
        )
        if (
            stored_record.value.manifest
            != manifest
        ):
            raise DurableBackupManifestConflict(
                "manifest_id already binds different content"
            )

        head_value = DurableBackupManifestHead(
            manifest.backup_name,
            manifest.generation,
            manifest.manifest_id,
            manifest.digest,
        )
        head_key = self._head_key(
            manifest.backup_name
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
                    head_value,
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
                DurableBackupManifestHead,
            ):
                raise DurableBackupManifestCorruption(
                    "backup head has invalid type"
                )
            if (
                current_record.value.generation
                != manifest.generation - 1
                or current_record.value.manifest_id
                != manifest.previous_manifest_id
                or current_record.value.manifest_digest
                != manifest.previous_manifest_digest
            ):
                raise DurableBackupManifestConflict(
                    "backup head changed during publication"
                )
            try:
                head_record = self.backend.compare_and_swap(
                    self.namespace,
                    head_key,
                    expected_revision=(
                        current_record.revision
                    ),
                    value=head_value,
                )
            except DistributedStateConflict as exc:
                raise DurableBackupManifestConflict(
                    "backup head CAS lost to concurrent publisher"
                ) from exc

        if (
            not isinstance(
                head_record.value,
                DurableBackupManifestHead,
            )
            or head_record.value != head_value
        ):
            raise DurableBackupManifestConflict(
                "published backup head differs from requested manifest"
            )
        return DurableBackupManifestPublication(
            StoredDurableBackupManifest(
                stored_record.revision,
                stored_record.value,
            ),
            head_record.revision,
            head_record.value,
            head_created,
        )

    def require(
        self,
        manifest_id: str,
    ) -> StoredDurableBackupManifest:
        stored = self.get(
            manifest_id
        )
        if stored is None:
            raise DurableBackupManifestConflict(
                "required backup manifest is missing"
            )
        return stored


class DurableBackupManifestBuilder:
    """Materialize deterministic hot-suffix commitments for a signed barrier."""

    def __init__(
        self,
        barrier_store: DurableConsistencyBarrierStore,
        manifest_store: DurableBackupManifestStore,
        *,
        policy: DurableBackupManifestPolicy
        | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            barrier_store,
            DurableConsistencyBarrierStore,
        ):
            raise TypeError(
                "barrier_store must be DurableConsistencyBarrierStore"
            )
        if not isinstance(
            manifest_store,
            DurableBackupManifestStore,
        ):
            raise TypeError(
                "manifest_store must be DurableBackupManifestStore"
            )
        self.barrier_store = barrier_store
        self.manifest_store = manifest_store
        self.policy = (
            policy
            or DurableBackupManifestPolicy()
        )
        if not isinstance(
            self.policy,
            DurableBackupManifestPolicy,
        ):
            raise TypeError(
                "policy must be DurableBackupManifestPolicy"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock

    def _entries(
        self,
        chains: Iterable[
            tuple[str, object]
        ],
    ) -> dict[str, object]:
        entries = tuple(chains)
        if len(entries) > self.policy.max_chains:
            raise DurableBackupManifestConflict(
                "backup chain bound exceeded"
            )
        result: dict[str, object] = {}
        for item in entries:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
            ):
                raise ValueError(
                    "backup chains must be (chain_id, chain) pairs"
                )
            chain_id, chain = item
            chain_id = _identity(
                "chain_id",
                chain_id,
                maximum=128,
            )
            if chain_id in result:
                raise ValueError(
                    "duplicate backup chain_id"
                )
            for method in (
                "verify",
                "head",
                "snapshot_segment",
                "verify_segment",
            ):
                if not callable(
                    getattr(chain, method, None)
                ):
                    raise TypeError(
                        f"chain {chain_id} does not implement {method}"
                    )
            result[chain_id] = chain
        return result

    def _segment(
        self,
        member: DurableConsistencyBarrierMember,
        chain: object,
    ) -> DurableBackupChainManifest:
        if (
            self.policy.require_chain_verify
            and not bool(chain.verify())
        ):
            raise DurableBackupManifestCorruption(
                f"chain {member.chain_id} failed integrity verification"
            )
        if self.policy.require_barrier_root_ancestor:
            ancestor = getattr(
                chain,
                "root_is_ancestor",
                None,
            )
            if not callable(ancestor):
                raise DurableBackupManifestConflict(
                    f"chain {member.chain_id} lacks root ancestry verification"
                )
            if not bool(
                ancestor(member.head_root)
            ):
                raise DurableBackupManifestConflict(
                    f"barrier root for {member.chain_id} is no longer a committed live ancestor"
                )

        prefix_required = (
            member.hot_floor_sequence > 0
        )
        if (
            prefix_required
            and self.policy.require_archive_for_compacted_prefix
            and (
                not member.hot_floor_archive_id
                or not member.hot_floor_archive_manifest_digest
            )
        ):
            raise DurableBackupManifestConflict(
                f"chain {member.chain_id} compacted prefix lacks archive authority"
            )
        expected_count = (
            member.head_sequence
            - member.hot_floor_sequence
        )
        if (
            expected_count
            > self.policy.max_segment_items
        ):
            raise DurableBackupManifestConflict(
                f"chain {member.chain_id} hot suffix exceeds backup bound"
            )
        segment = chain.snapshot_segment(
            member.hot_floor_root,
            member.head_root,
            max_items=(
                self.policy.max_segment_items
            ),
        )
        if len(segment) != expected_count:
            raise DurableBackupManifestCorruption(
                f"chain {member.chain_id} segment length differs from barrier interval"
            )
        if not bool(
            chain.verify_segment(
                member.hot_floor_root,
                member.head_root,
                max_items=(
                    self.policy.max_segment_items
                ),
            )
        ):
            raise DurableBackupManifestCorruption(
                f"chain {member.chain_id} barrier segment failed verification"
            )
        if segment:
            first_sequence = int(
                segment[0].sequence
            )
            last_sequence = int(
                segment[-1].sequence
            )
            if (
                first_sequence
                != member.hot_floor_sequence + 1
                or last_sequence
                != member.head_sequence
            ):
                raise DurableBackupManifestCorruption(
                    f"chain {member.chain_id} segment sequence boundaries differ"
                )
        canonical = [
            _canonical_item(item)
            for item in segment
        ]
        segment_digest = _stable_digest(
            canonical
        )
        return DurableBackupChainManifest(
            member.chain_id,
            member.digest,
            member.head_sequence,
            member.head_root,
            prefix_required,
            member.hot_floor_archive_id,
            member.hot_floor_archive_manifest_digest,
            member.hot_floor_sequence,
            member.hot_floor_root,
            member.head_sequence,
            member.head_root,
            len(segment),
            segment_digest,
        )

    def build(
        self,
        backup_name: str,
        barrier_id: str,
        chains: Iterable[
            tuple[str, object]
        ],
        *,
        operator_id: str,
    ) -> DurableBackupManifestPublication:
        backup_name = _identity(
            "backup_name",
            backup_name,
            maximum=256,
        )
        operator_id = _identity(
            "operator_id",
            operator_id,
            maximum=256,
        )
        stored_barrier = self.barrier_store.require(
            barrier_id
        )
        barrier = stored_barrier.signed.barrier
        by_id = self._entries(chains)
        barrier_ids = {
            member.chain_id
            for member in barrier.members
        }
        if set(by_id) != barrier_ids:
            raise DurableBackupManifestConflict(
                "backup chain set differs from consistency barrier"
            )
        chain_manifests = tuple(
            self._segment(
                member,
                by_id[member.chain_id],
            )
            for member in barrier.members
        )

        current = self.manifest_store.current(
            backup_name
        )
        if current is None:
            generation = 1
            previous_id = ""
            previous_digest = ""
        else:
            prior = current.signed.manifest
            generation = prior.generation + 1
            previous_id = prior.manifest_id
            previous_digest = prior.digest

        created_at = _timestamp(
            "created_at",
            self._clock(),
        )
        manifest_id = DurableBackupManifest.derive_id(
            backup_name=backup_name,
            generation=generation,
            previous_manifest_id=previous_id,
            previous_manifest_digest=(
                previous_digest
            ),
            barrier_id=barrier.barrier_id,
            barrier_digest=barrier.digest,
            barrier_name=barrier.barrier_name,
            barrier_generation=barrier.generation,
            operator_id=operator_id,
            created_at=created_at,
            policy_digest=self.policy.digest,
            chains=chain_manifests,
        )
        manifest = DurableBackupManifest(
            1,
            manifest_id,
            backup_name,
            generation,
            previous_id,
            previous_digest,
            barrier.barrier_id,
            barrier.digest,
            barrier.barrier_name,
            barrier.generation,
            operator_id,
            created_at,
            self.policy.digest,
            chain_manifests,
            False,
            False,
        )
        return self.manifest_store.publish(
            manifest
        )
