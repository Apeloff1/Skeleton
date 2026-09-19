"""CAS-backed persistence and lineage for post-compaction audit proofs.

A proof is immutable once signed. The store adds three durable indexes:
proof id to exact signed proof, workflow id to exact proof id, and chain id to
an append-only generation lineage plus a CAS latest head.

Writes are restart-idempotent. The lineage head commits before its generation
index. If a process dies in that narrow window, a fresh reader reconstructs the
missing latest index from the signed proof and the head commitment. This avoids
orphan generation slots that could block a competing writer.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_archive import (
    DurableArchiveVerification,
    SignedDurableArchiveManifest,
)
from skeleton.shells.ai.durable_compaction_certificate import (
    SignedDurableCompactionCertificate,
)
from skeleton.shells.ai.durable_compaction_operator import (
    DurableCompactionWorkflow,
)
from skeleton.shells.ai.durable_compaction_proof import (
    DurableCompactionProofBuilder,
    SignedDurableCompactionProof,
)
from skeleton.shells.ai.durable_compaction_reservation import (
    SignedDurableCompactionReservation,
)
from skeleton.shells.ai.durable_pruning import DurablePruningResult
from skeleton.shells.ai.durable_pruning_authorization import (
    SignedDurablePruningAuthorization,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(name: str, value: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


def _identity(name: str, value: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class StoredDurableCompactionProof:
    revision: int
    proof: SignedDurableCompactionProof
    stored_at: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "proof revision must be positive integer"
            )
        if not isinstance(
            self.proof,
            SignedDurableCompactionProof,
        ):
            raise TypeError(
                "proof must be SignedDurableCompactionProof"
            )
        if (
            isinstance(self.stored_at, bool)
            or not isinstance(self.stored_at, (int, float))
            or not math.isfinite(float(self.stored_at))
            or float(self.stored_at) < 0.0
        ):
            raise ValueError(
                "proof stored_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "stored_at",
            float(self.stored_at),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "proof": self.proof.to_dict(),
            "stored_at": self.stored_at,
        }


@dataclass(frozen=True)
class DurableCompactionProofWorkflowIndex:
    workflow_id: str
    chain_id: str
    proof_id: str
    proof_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workflow_id",
            _digest(
                "workflow_id",
                self.workflow_id,
            ),
        )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "proof_id",
            _digest("proof_id", self.proof_id),
        )
        object.__setattr__(
            self,
            "proof_digest",
            _digest(
                "proof_digest",
                self.proof_digest,
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "workflow_id": self.workflow_id,
            "chain_id": self.chain_id,
            "proof_id": self.proof_id,
            "proof_digest": self.proof_digest,
        }


@dataclass(frozen=True)
class DurableCompactionProofLineageEntry:
    chain_id: str
    generation: int
    proof_id: str
    proof_digest: str
    workflow_id: str
    previous_proof_id: str
    stored_at: float

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError(
                "proof lineage generation must be positive"
            )
        for name in (
            "proof_id",
            "proof_digest",
            "workflow_id",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        if self.previous_proof_id:
            object.__setattr__(
                self,
                "previous_proof_id",
                _digest(
                    "previous_proof_id",
                    self.previous_proof_id,
                ),
            )
        if (
            isinstance(self.stored_at, bool)
            or not isinstance(self.stored_at, (int, float))
            or not math.isfinite(float(self.stored_at))
            or float(self.stored_at) < 0.0
        ):
            raise ValueError(
                "lineage stored_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "stored_at",
            float(self.stored_at),
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "generation": self.generation,
            "proof_id": self.proof_id,
            "proof_digest": self.proof_digest,
            "workflow_id": self.workflow_id,
            "previous_proof_id": self.previous_proof_id,
            "stored_at": self.stored_at,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableCompactionProofHead:
    chain_id: str
    generation: int
    proof_id: str
    entry_digest: str

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError(
                "proof head generation must be positive"
            )
        object.__setattr__(
            self,
            "proof_id",
            _digest("proof_id", self.proof_id),
        )
        object.__setattr__(
            self,
            "entry_digest",
            _digest(
                "entry_digest",
                self.entry_digest,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "generation": self.generation,
            "proof_id": self.proof_id,
            "entry_digest": self.entry_digest,
        }


@dataclass(frozen=True)
class DurableCompactionProofStoreResult:
    stored: StoredDurableCompactionProof
    workflow_index: DurableCompactionProofWorkflowIndex
    lineage_entry: DurableCompactionProofLineageEntry
    head_revision: int
    head: DurableCompactionProofHead
    fresh_proof: bool
    repaired_indexes: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.head_revision, bool)
            or not isinstance(self.head_revision, int)
            or self.head_revision <= 0
        ):
            raise ValueError(
                "proof head revision must be positive"
            )
        if not isinstance(self.fresh_proof, bool):
            raise ValueError("fresh_proof must be bool")
        if (
            isinstance(self.repaired_indexes, bool)
            or not isinstance(self.repaired_indexes, int)
            or self.repaired_indexes < 0
        ):
            raise ValueError(
                "repaired_indexes must be non-negative"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "workflow_index": (
                self.workflow_index.to_dict()
            ),
            "lineage_entry": (
                self.lineage_entry.to_dict()
            ),
            "head_revision": self.head_revision,
            "head": self.head.to_dict(),
            "fresh_proof": self.fresh_proof,
            "repaired_indexes": self.repaired_indexes,
        }


class DurableCompactionProofStoreError(RuntimeError):
    pass


class DurableCompactionProofStoreConflict(
    DurableCompactionProofStoreError
):
    pass


class DurableCompactionProofStore:
    """Persist verified single-chain compaction proofs and their lineage."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        builder: DurableCompactionProofBuilder,
        *,
        namespace: str = "shell-ai-durable-compaction-proofs",
        max_proofs_per_chain: int = 100_000,
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            backend,
            VersionedStateBackend,
        ):
            raise TypeError(
                "backend must satisfy VersionedStateBackend"
            )
        if not isinstance(
            builder,
            DurableCompactionProofBuilder,
        ):
            raise TypeError(
                "builder must be DurableCompactionProofBuilder"
            )
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid compaction proof namespace"
            )
        if (
            isinstance(max_proofs_per_chain, bool)
            or not isinstance(max_proofs_per_chain, int)
            or max_proofs_per_chain <= 0
        ):
            raise ValueError(
                "max_proofs_per_chain must be positive integer"
            )
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.builder = builder
        self.namespace = namespace
        self.max_proofs_per_chain = max_proofs_per_chain
        self.max_cas_retries = max_cas_retries
        self._clock = clock

    @staticmethod
    def _proof_key(proof_id: str) -> str:
        return "proof:" + _digest(
            "proof_id",
            proof_id,
        )

    @staticmethod
    def _workflow_key(workflow_id: str) -> str:
        return "workflow:" + _digest(
            "workflow_id",
            workflow_id,
        )

    @staticmethod
    def _chain_hash(chain_id: str) -> str:
        return _hash_key(
            _identity(
                "chain_id",
                chain_id,
                maximum=128,
            )
        )

    @classmethod
    def _head_key(cls, chain_id: str) -> str:
        return "head:" + cls._chain_hash(chain_id)

    @classmethod
    def _entry_key(
        cls,
        chain_id: str,
        generation: int,
    ) -> str:
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation <= 0
        ):
            raise ValueError(
                "generation must be positive integer"
            )
        return (
            "lineage:"
            + cls._chain_hash(chain_id)
            + f":{generation:020d}"
        )

    def _now(self) -> float:
        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            raise ValueError(
                "proof store clock must return finite non-negative time"
            )
        return float(value)

    @staticmethod
    def _workflow_index(
        value,
    ) -> DurableCompactionProofWorkflowIndex:
        if not isinstance(
            value,
            DurableCompactionProofWorkflowIndex,
        ):
            raise DurableCompactionProofStoreError(
                "workflow proof index has invalid value type"
            )
        return value

    @staticmethod
    def _entry(
        value,
    ) -> DurableCompactionProofLineageEntry:
        if not isinstance(
            value,
            DurableCompactionProofLineageEntry,
        ):
            raise DurableCompactionProofStoreError(
                "proof lineage entry has invalid value type"
            )
        return value

    @staticmethod
    def _head(
        value,
    ) -> DurableCompactionProofHead:
        if not isinstance(
            value,
            DurableCompactionProofHead,
        ):
            raise DurableCompactionProofStoreError(
                "proof lineage head has invalid value type"
            )
        return value

    def get(
        self,
        proof_id: str,
    ) -> StoredDurableCompactionProof | None:
        record = self.backend.get(
            self.namespace,
            self._proof_key(proof_id),
        )
        if record is None:
            return None
        if (
            not isinstance(record.value, tuple)
            or len(record.value) != 2
        ):
            raise DurableCompactionProofStoreError(
                "proof record has invalid value type"
            )
        item, stored_at = record.value
        if not isinstance(
            item,
            SignedDurableCompactionProof,
        ):
            raise DurableCompactionProofStoreError(
                "proof record does not contain signed proof"
            )
        if item.proof_id != proof_id:
            raise DurableCompactionProofStoreError(
                "proof key/id mismatch"
            )
        return StoredDurableCompactionProof(
            record.revision,
            item,
            float(stored_at),
        )

    def by_workflow(
        self,
        workflow_id: str,
    ) -> StoredDurableCompactionProof | None:
        record = self.backend.get(
            self.namespace,
            self._workflow_key(workflow_id),
        )
        if record is None:
            return None
        index = self._workflow_index(record.value)
        if index.workflow_id != workflow_id:
            raise DurableCompactionProofStoreError(
                "workflow proof index identity mismatch"
            )
        stored = self.get(index.proof_id)
        if stored is None:
            raise DurableCompactionProofStoreError(
                "workflow index references missing proof"
            )
        if (
            stored.proof.proof.digest
            != index.proof_digest
        ):
            raise DurableCompactionProofStoreError(
                "workflow index proof digest mismatch"
            )
        return stored

    def head(
        self,
        chain_id: str,
    ) -> tuple[int, DurableCompactionProofHead] | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(chain_id),
        )
        if record is None:
            return None
        head = self._head(record.value)
        if head.chain_id != chain_id:
            raise DurableCompactionProofStoreError(
                "proof head chain mismatch"
            )
        return record.revision, head

    def latest(
        self,
        chain_id: str,
    ) -> StoredDurableCompactionProof | None:
        current = self.head(chain_id)
        if current is None:
            return None
        _, head = current
        stored = self.get(head.proof_id)
        if stored is None:
            raise DurableCompactionProofStoreError(
                "proof head references missing proof"
            )
        return stored

    def _put_lineage_entry(
        self,
        entry: DurableCompactionProofLineageEntry,
    ) -> bool:
        key = self._entry_key(
            entry.chain_id,
            entry.generation,
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    entry,
                )
                return True
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
        current = self._entry(existing.value)
        if current != entry:
            raise DurableCompactionProofStoreConflict(
                "proof lineage generation binds different entry"
            )
        return False

    def _repair_latest_entry(
        self,
        head: DurableCompactionProofHead,
    ) -> DurableCompactionProofLineageEntry:
        key = self._entry_key(
            head.chain_id,
            head.generation,
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is not None:
            entry = self._entry(existing.value)
            if entry.digest != head.entry_digest:
                raise DurableCompactionProofStoreError(
                    "proof head entry digest mismatch"
                )
            return entry

        stored = self.get(head.proof_id)
        if stored is None:
            raise DurableCompactionProofStoreError(
                "proof head references missing proof"
            )
        if head.generation == 1:
            previous_proof_id = ""
        else:
            prior_record = self.backend.get(
                self.namespace,
                self._entry_key(
                    head.chain_id,
                    head.generation - 1,
                ),
            )
            if prior_record is None:
                raise DurableCompactionProofStoreError(
                    "cannot repair latest proof entry without prior lineage"
                )
            prior = self._entry(
                prior_record.value
            )
            previous_proof_id = (
                prior.proof_id
            )
        proof = stored.proof.proof
        entry = DurableCompactionProofLineageEntry(
            head.chain_id,
            head.generation,
            proof.proof_id,
            proof.digest,
            proof.workflow_id,
            previous_proof_id,
            stored.stored_at,
        )
        if entry.digest != head.entry_digest:
            raise DurableCompactionProofStoreError(
                "reconstructed proof lineage entry differs from head"
            )
        self._put_lineage_entry(entry)
        return entry

    def lineage(
        self,
        chain_id: str,
    ) -> tuple[
        DurableCompactionProofLineageEntry,
        ...,
    ]:
        current = self.head(chain_id)
        if current is None:
            return ()
        _, head = current
        if (
            head.generation
            > self.max_proofs_per_chain
        ):
            raise DurableCompactionProofStoreError(
                "proof head exceeds configured lineage bound"
            )
        self._repair_latest_entry(head)
        entries: list[
            DurableCompactionProofLineageEntry
        ] = []
        previous_proof_id = ""
        for generation in range(
            1,
            head.generation + 1,
        ):
            record = self.backend.get(
                self.namespace,
                self._entry_key(
                    chain_id,
                    generation,
                ),
            )
            if record is None:
                raise DurableCompactionProofStoreError(
                    "proof lineage generation is missing"
                )
            entry = self._entry(record.value)
            if (
                entry.chain_id != chain_id
                or entry.generation
                != generation
            ):
                raise DurableCompactionProofStoreError(
                    "proof lineage entry identity mismatch"
                )
            if (
                entry.previous_proof_id
                != previous_proof_id
            ):
                raise DurableCompactionProofStoreError(
                    "proof lineage previous id is not contiguous"
                )
            stored = self.get(
                entry.proof_id
            )
            if stored is None:
                raise DurableCompactionProofStoreError(
                    "proof lineage references missing proof"
                )
            proof = stored.proof.proof
            if proof.digest != entry.proof_digest:
                raise DurableCompactionProofStoreError(
                    "proof lineage digest mismatch"
                )
            if (
                proof.workflow_id
                != entry.workflow_id
                or proof.chain_id
                != entry.chain_id
            ):
                raise DurableCompactionProofStoreError(
                    "proof lineage authority binding mismatch"
                )
            entries.append(entry)
            previous_proof_id = (
                entry.proof_id
            )
        final = entries[-1]
        if (
            final.proof_id
            != head.proof_id
            or final.digest
            != head.entry_digest
        ):
            raise DurableCompactionProofStoreError(
                "proof lineage head differs from final entry"
            )
        return tuple(entries)

    def verify_lineage(
        self,
        chain_id: str,
    ) -> bool:
        try:
            self.lineage(chain_id)
            return True
        except (
            DurableCompactionProofStoreError,
            ValueError,
            TypeError,
        ):
            return False

    def _put_proof(
        self,
        item: SignedDurableCompactionProof,
        stored_at: float,
    ) -> tuple[
        StoredDurableCompactionProof,
        bool,
    ]:
        key = self._proof_key(
            item.proof_id
        )
        value = (item, stored_at)
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                written = (
                    self.backend.put_if_absent(
                        self.namespace,
                        key,
                        value,
                    )
                )
                return (
                    StoredDurableCompactionProof(
                        written.revision,
                        item,
                        stored_at,
                    ),
                    True,
                )
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
        if (
            not isinstance(existing.value, tuple)
            or len(existing.value) != 2
        ):
            raise DurableCompactionProofStoreError(
                "proof record has invalid value type"
            )
        stored_item, prior_time = (
            existing.value
        )
        if stored_item != item:
            raise DurableCompactionProofStoreConflict(
                "proof_id already binds different signed proof"
            )
        return (
            StoredDurableCompactionProof(
                existing.revision,
                stored_item,
                float(prior_time),
            ),
            False,
        )

    def _put_workflow_index(
        self,
        item: SignedDurableCompactionProof,
    ) -> tuple[
        DurableCompactionProofWorkflowIndex,
        bool,
    ]:
        proof = item.proof
        index = (
            DurableCompactionProofWorkflowIndex(
                proof.workflow_id,
                proof.chain_id,
                proof.proof_id,
                proof.digest,
            )
        )
        key = self._workflow_key(
            proof.workflow_id
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    index,
                )
                return index, True
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
        current = self._workflow_index(
            existing.value
        )
        if current != index:
            raise DurableCompactionProofStoreConflict(
                "workflow already binds a different compaction proof"
            )
        return current, False

    def _find_existing_lineage(
        self,
        chain_id: str,
        proof_id: str,
    ) -> DurableCompactionProofLineageEntry | None:
        for entry in self.lineage(
            chain_id
        ):
            if entry.proof_id == proof_id:
                return entry
        return None

    def _append_lineage(
        self,
        item: SignedDurableCompactionProof,
        stored_at: float,
    ) -> tuple[
        int,
        DurableCompactionProofHead,
        DurableCompactionProofLineageEntry,
        bool,
    ]:
        proof = item.proof
        existing_entry = (
            self._find_existing_lineage(
                proof.chain_id,
                proof.proof_id,
            )
        )
        if existing_entry is not None:
            current = self.head(
                proof.chain_id
            )
            if current is None:
                raise DurableCompactionProofStoreError(
                    "existing lineage has no head"
                )
            revision, head = current
            return (
                revision,
                head,
                existing_entry,
                False,
            )

        for _ in range(
            self.max_cas_retries
        ):
            current = self.head(
                proof.chain_id
            )
            if current is None:
                revision = 0
                generation = 1
                previous_proof_id = ""
            else:
                revision, head = current
                self._repair_latest_entry(
                    head
                )
                generation = (
                    head.generation + 1
                )
                previous_proof_id = (
                    head.proof_id
                )
            if (
                generation
                > self.max_proofs_per_chain
            ):
                raise DurableCompactionProofStoreError(
                    "proof lineage capacity exhausted"
                )
            entry = (
                DurableCompactionProofLineageEntry(
                    proof.chain_id,
                    generation,
                    proof.proof_id,
                    proof.digest,
                    proof.workflow_id,
                    previous_proof_id,
                    stored_at,
                )
            )
            next_head = DurableCompactionProofHead(
                proof.chain_id,
                generation,
                proof.proof_id,
                entry.digest,
            )
            try:
                if revision == 0:
                    written = (
                        self.backend.put_if_absent(
                            self.namespace,
                            self._head_key(
                                proof.chain_id
                            ),
                            next_head,
                        )
                    )
                else:
                    written = (
                        self.backend.compare_and_swap(
                            self.namespace,
                            self._head_key(
                                proof.chain_id
                            ),
                            expected_revision=revision,
                            value=next_head,
                        )
                    )
            except DistributedStateConflict:
                existing_entry = (
                    self._find_existing_lineage(
                        proof.chain_id,
                        proof.proof_id,
                    )
                )
                if existing_entry is not None:
                    current = self.head(
                        proof.chain_id
                    )
                    if current is None:
                        raise DurableCompactionProofStoreError(
                            "proof lineage lost head after race"
                        )
                    current_revision, current_head = (
                        current
                    )
                    return (
                        current_revision,
                        current_head,
                        existing_entry,
                        False,
                    )
                continue

            self._put_lineage_entry(
                entry
            )
            return (
                written.revision,
                next_head,
                entry,
                True,
            )
        raise DurableCompactionProofStoreConflict(
            "proof lineage head CAS retry bound exhausted"
        )

    def put(
        self,
        item: SignedDurableCompactionProof,
        *,
        workflow: DurableCompactionWorkflow,
        reservation: SignedDurableCompactionReservation,
        certificate: SignedDurableCompactionCertificate,
        authorization: SignedDurablePruningAuthorization,
        archive: SignedDurableArchiveManifest,
        archive_verification: DurableArchiveVerification,
        pruning: DurablePruningResult,
    ) -> DurableCompactionProofStoreResult:
        if not isinstance(
            item,
            SignedDurableCompactionProof,
        ):
            raise TypeError(
                "item must be SignedDurableCompactionProof"
            )
        self.builder.require(
            item,
            workflow=workflow,
            reservation=reservation,
            certificate=certificate,
            authorization=authorization,
            archive=archive,
            archive_verification=archive_verification,
            pruning=pruning,
        )
        stored_at = self._now()
        stored, fresh = self._put_proof(
            item,
            stored_at,
        )
        repaired = 0
        workflow_index, wrote_workflow = (
            self._put_workflow_index(
                item
            )
        )
        if wrote_workflow and not fresh:
            repaired += 1
        (
            head_revision,
            head,
            lineage_entry,
            wrote_lineage,
        ) = self._append_lineage(
            item,
            stored.stored_at,
        )
        if wrote_lineage and not fresh:
            repaired += 1
        if not self.verify_lineage(
            item.proof.chain_id
        ):
            raise DurableCompactionProofStoreError(
                "proof lineage failed verification after write"
            )
        return DurableCompactionProofStoreResult(
            stored,
            workflow_index,
            lineage_entry,
            head_revision,
            head,
            fresh,
            repaired,
        )

    def require(
        self,
        proof_id: str,
    ) -> StoredDurableCompactionProof:
        stored = self.get(proof_id)
        if stored is None:
            raise DurableCompactionProofStoreError(
                "required compaction proof is missing"
            )
        indexed = self.by_workflow(
            stored.proof.proof.workflow_id
        )
        if indexed is None:
            raise DurableCompactionProofStoreError(
                "required proof workflow index is missing"
            )
        if indexed.proof.proof_id != proof_id:
            raise DurableCompactionProofStoreError(
                "required proof workflow index differs"
            )
        lineage = self.lineage(
            stored.proof.proof.chain_id
        )
        if not any(
            entry.proof_id == proof_id
            for entry in lineage
        ):
            raise DurableCompactionProofStoreError(
                "required proof is absent from chain lineage"
            )
        return stored
