"""Serializable worker checkpoint state with integrity digests."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping


class CheckpointError(ValueError):
    pass


def _canonical(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class WorkerCheckpoint:
    worker_id: str
    generation: int
    sequence: int
    queue_claim_ids: tuple[str, ...] = ()
    completed_items: int = 0
    failed_items: int = 0
    metadata: Mapping[str, str] = field(default_factory=dict)
    previous_digest: str = ""
    digest: str = ""

    def __post_init__(self) -> None:
        if not self.worker_id or len(self.worker_id) > 128:
            raise CheckpointError("invalid worker_id")
        if self.generation <= 0 or self.sequence <= 0:
            raise CheckpointError("generation and sequence must be positive")
        if self.completed_items < 0 or self.failed_items < 0:
            raise CheckpointError("checkpoint counters may not be negative")
        claims = tuple(self.queue_claim_ids)
        if len(claims) > 4096:
            raise CheckpointError("too many checkpoint claim IDs")
        if any(not isinstance(value, str) or not value or len(value) > 256 for value in claims):
            raise CheckpointError("invalid checkpoint claim ID")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise CheckpointError("too many checkpoint metadata fields")
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or len(key) > 128
            or len(value) > 1024
            for key, value in metadata.items()
        ):
            raise CheckpointError("invalid checkpoint metadata")
        object.__setattr__(self, "queue_claim_ids", claims)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "generation": self.generation,
            "sequence": self.sequence,
            "queue_claim_ids": list(self.queue_claim_ids),
            "completed_items": self.completed_items,
            "failed_items": self.failed_items,
            "metadata": dict(self.metadata),
            "previous_digest": self.previous_digest,
        }

    def expected_digest(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict()).encode("utf-8")).hexdigest()

    @property
    def valid(self) -> bool:
        return bool(self.digest) and self.digest == self.expected_digest()

    def to_dict(self) -> dict[str, object]:
        payload = self.unsigned_dict()
        payload["digest"] = self.digest
        return payload

    @classmethod
    def create(
        cls,
        *,
        worker_id: str,
        generation: int,
        sequence: int,
        queue_claim_ids: tuple[str, ...] = (),
        completed_items: int = 0,
        failed_items: int = 0,
        metadata: Mapping[str, str] | None = None,
        previous_digest: str = "",
    ) -> "WorkerCheckpoint":
        provisional = cls(
            worker_id=worker_id,
            generation=generation,
            sequence=sequence,
            queue_claim_ids=queue_claim_ids,
            completed_items=completed_items,
            failed_items=failed_items,
            metadata=metadata or {},
            previous_digest=previous_digest,
        )
        return cls(**provisional.unsigned_dict(), digest=provisional.expected_digest())

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "WorkerCheckpoint":
        try:
            checkpoint = cls(
                worker_id=str(payload["worker_id"]),
                generation=int(payload["generation"]),
                sequence=int(payload["sequence"]),
                queue_claim_ids=tuple(str(value) for value in payload.get("queue_claim_ids", ())),
                completed_items=int(payload.get("completed_items", 0)),
                failed_items=int(payload.get("failed_items", 0)),
                metadata={str(k): str(v) for k, v in dict(payload.get("metadata", {})).items()},
                previous_digest=str(payload.get("previous_digest", "")),
                digest=str(payload.get("digest", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CheckpointError("invalid checkpoint payload") from exc
        if not checkpoint.valid:
            raise CheckpointError("checkpoint digest mismatch")
        return checkpoint


class CheckpointChain:
    """Generation-local chain that rejects rollback and forks."""

    def __init__(self, worker_id: str, generation: int, *, max_checkpoints: int = 10000) -> None:
        if max_checkpoints <= 0:
            raise ValueError("max_checkpoints must be positive")
        self.worker_id = worker_id
        self.generation = generation
        self.max_checkpoints = max_checkpoints
        self._items: list[WorkerCheckpoint] = []

    def append(
        self,
        *,
        queue_claim_ids: tuple[str, ...] = (),
        completed_items: int = 0,
        failed_items: int = 0,
        metadata: Mapping[str, str] | None = None,
    ) -> WorkerCheckpoint:
        if len(self._items) >= self.max_checkpoints:
            raise CheckpointError("checkpoint chain capacity exhausted")
        previous = "" if not self._items else self._items[-1].digest
        checkpoint = WorkerCheckpoint.create(
            worker_id=self.worker_id,
            generation=self.generation,
            sequence=len(self._items) + 1,
            queue_claim_ids=queue_claim_ids,
            completed_items=completed_items,
            failed_items=failed_items,
            metadata=metadata,
            previous_digest=previous,
        )
        self._items.append(checkpoint)
        return checkpoint

    def restore(self, checkpoint: WorkerCheckpoint) -> None:
        if checkpoint.worker_id != self.worker_id or checkpoint.generation != self.generation:
            raise CheckpointError("checkpoint identity mismatch")
        if not checkpoint.valid:
            raise CheckpointError("checkpoint digest mismatch")
        if self._items:
            head = self._items[-1]
            if checkpoint.sequence <= head.sequence:
                raise CheckpointError("checkpoint rollback is not allowed")
            if checkpoint.previous_digest != head.digest:
                raise CheckpointError("checkpoint fork detected")
        elif checkpoint.sequence != 1 or checkpoint.previous_digest:
            raise CheckpointError("first checkpoint must start a new chain")
        self._items.append(checkpoint)

    def verify(self) -> bool:
        previous = ""
        for index, checkpoint in enumerate(self._items, start=1):
            if checkpoint.sequence != index:
                return False
            if checkpoint.previous_digest != previous:
                return False
            if not checkpoint.valid:
                return False
            previous = checkpoint.digest
        return True

    @property
    def head(self) -> WorkerCheckpoint | None:
        return None if not self._items else self._items[-1]

    def snapshot(self) -> tuple[WorkerCheckpoint, ...]:
        return tuple(self._items)
