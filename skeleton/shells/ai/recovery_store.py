"""Durable immutable recovery checkpoints with monotonic per-session heads."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.recovery_checkpoint import AIRecoveryCheckpoint
from skeleton.shells.ai.store_protocol import VersionedStateBackend


@dataclass(frozen=True)
class RecoveryCheckpointRecord:
    finalization_id: str
    session_id: str
    checkpoint: AIRecoveryCheckpoint
    stored_at: float

    def __post_init__(self) -> None:
        if not self.finalization_id or len(self.finalization_id) > 256:
            raise ValueError("invalid recovery finalization_id")
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("invalid recovery session_id")
        if self.checkpoint.session.session_id != self.session_id:
            raise ValueError("recovery checkpoint session binding mismatch")
        if (
            isinstance(self.stored_at, bool)
            or not isinstance(self.stored_at, (int, float))
            or not math.isfinite(float(self.stored_at))
            or float(self.stored_at) < 0.0
        ):
            raise ValueError("stored_at must be finite and non-negative")
        object.__setattr__(self, "stored_at", float(self.stored_at))

    @property
    def digest(self) -> str:
        raw = json.dumps(
            {
                "finalization_id": self.finalization_id,
                "session_id": self.session_id,
                "checkpoint_digest": self.checkpoint.digest,
                "stored_at": self.stored_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "finalization_id": self.finalization_id,
            "session_id": self.session_id,
            "checkpoint": self.checkpoint.to_dict(),
            "checkpoint_digest": self.checkpoint.digest,
            "stored_at": self.stored_at,
            "record_digest": self.digest,
        }


@dataclass(frozen=True)
class RecoveryCheckpointHead:
    session_id: str
    finalization_id: str
    checkpoint_digest: str
    transition_count: int

    def __post_init__(self) -> None:
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("invalid recovery head session_id")
        if not self.finalization_id or len(self.finalization_id) > 256:
            raise ValueError("invalid recovery head finalization_id")
        if len(self.checkpoint_digest) != 64:
            raise ValueError("checkpoint_digest must be SHA-256 hex")
        # Treat the digest as an opaque 64-character authority token.
        if (
            isinstance(self.transition_count, bool)
            or not isinstance(self.transition_count, int)
            or self.transition_count < 0
        ):
            raise ValueError("transition_count must be non-negative integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "finalization_id": self.finalization_id,
            "checkpoint_digest": self.checkpoint_digest,
            "transition_count": self.transition_count,
        }


@dataclass(frozen=True)
class StoredRecoveryCheckpoint:
    revision: int
    record: RecoveryCheckpointRecord

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError("recovery checkpoint revision must be positive")


@dataclass(frozen=True)
class RecoveryCheckpointCommit:
    stored: StoredRecoveryCheckpoint
    head_revision: int
    head: RecoveryCheckpointHead
    head_advanced: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "stored_revision": self.stored.revision,
            "record": self.stored.record.to_dict(),
            "head_revision": self.head_revision,
            "head": self.head.to_dict(),
            "head_advanced": self.head_advanced,
        }


class RecoveryCheckpointConflict(RuntimeError):
    pass


class AIRecoveryCheckpointStore:
    """Persist exact recovery checkpoints and reject session-head rollback."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-recovery-checkpoint",
        max_retries: int = 16,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid recovery checkpoint namespace")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 1 <= max_retries <= 64
        ):
            raise ValueError("max_retries outside supported range")
        self.backend = backend
        self.namespace = namespace
        self.max_retries = max_retries
        self._clock = clock

    @staticmethod
    def _item_key(finalization_id: str) -> str:
        if not finalization_id or len(finalization_id) > 256:
            raise ValueError("invalid finalization_id")
        return "item:" + hashlib.sha256(
            finalization_id.encode()
        ).hexdigest()

    @staticmethod
    def _head_key(session_id: str) -> str:
        if not session_id or len(session_id) > 160:
            raise ValueError("invalid session_id")
        return "head:" + hashlib.sha256(
            session_id.encode()
        ).hexdigest()

    def get(
        self,
        finalization_id: str,
    ) -> StoredRecoveryCheckpoint | None:
        record = self.backend.get(
            self.namespace,
            self._item_key(finalization_id),
        )
        if record is None:
            return None
        if not isinstance(record.value, RecoveryCheckpointRecord):
            raise RuntimeError(
                "recovery checkpoint backend value type mismatch"
            )
        return StoredRecoveryCheckpoint(
            record.revision,
            record.value,
        )

    def head(
        self,
        session_id: str,
    ) -> tuple[int, RecoveryCheckpointHead] | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(session_id),
        )
        if record is None:
            return None
        if not isinstance(record.value, RecoveryCheckpointHead):
            raise RuntimeError("recovery checkpoint head type mismatch")
        return record.revision, record.value

    def _store_item(
        self,
        finalization_id: str,
        checkpoint: AIRecoveryCheckpoint,
    ) -> StoredRecoveryCheckpoint:
        key = self._item_key(finalization_id)
        existing = self.backend.get(self.namespace, key)
        if existing is not None:
            if not isinstance(existing.value, RecoveryCheckpointRecord):
                raise RuntimeError(
                    "recovery checkpoint backend value type mismatch"
                )
            if existing.value.checkpoint.digest != checkpoint.digest:
                raise RecoveryCheckpointConflict(
                    "finalization_id already binds different recovery checkpoint"
                )
            return StoredRecoveryCheckpoint(
                existing.revision,
                existing.value,
            )

        item = RecoveryCheckpointRecord(
            finalization_id,
            checkpoint.session.session_id,
            checkpoint,
            self._clock(),
        )
        try:
            stored = self.backend.put_if_absent(
                self.namespace,
                key,
                item,
            )
            return StoredRecoveryCheckpoint(
                stored.revision,
                item,
            )
        except DistributedStateConflict:
            winner = self.backend.get(self.namespace, key)
            if winner is None or not isinstance(
                winner.value,
                RecoveryCheckpointRecord,
            ):
                raise
            if winner.value.checkpoint.digest != checkpoint.digest:
                raise RecoveryCheckpointConflict(
                    "concurrent recovery checkpoint differs"
                )
            return StoredRecoveryCheckpoint(
                winner.revision,
                winner.value,
            )

    @staticmethod
    def _candidate_head(
        finalization_id: str,
        checkpoint: AIRecoveryCheckpoint,
    ) -> RecoveryCheckpointHead:
        return RecoveryCheckpointHead(
            checkpoint.session.session_id,
            finalization_id,
            checkpoint.digest,
            checkpoint.session.transition_count,
        )

    def put(
        self,
        finalization_id: str,
        checkpoint: AIRecoveryCheckpoint,
    ) -> RecoveryCheckpointCommit:
        if not isinstance(checkpoint, AIRecoveryCheckpoint):
            raise TypeError("checkpoint must be AIRecoveryCheckpoint")
        stored = self._store_item(
            finalization_id,
            checkpoint,
        )
        candidate = self._candidate_head(
            finalization_id,
            checkpoint,
        )
        head_key = self._head_key(candidate.session_id)

        for _ in range(self.max_retries):
            current_record = self.backend.get(
                self.namespace,
                head_key,
            )
            if current_record is None:
                try:
                    head_record = self.backend.put_if_absent(
                        self.namespace,
                        head_key,
                        candidate,
                    )
                    return RecoveryCheckpointCommit(
                        stored,
                        head_record.revision,
                        candidate,
                        True,
                    )
                except DistributedStateConflict:
                    continue

            current = current_record.value
            if not isinstance(current, RecoveryCheckpointHead):
                raise RuntimeError(
                    "recovery checkpoint head type mismatch"
                )
            if current.session_id != candidate.session_id:
                raise RecoveryCheckpointConflict(
                    "recovery checkpoint head session mismatch"
                )

            if current.transition_count > candidate.transition_count:
                return RecoveryCheckpointCommit(
                    stored,
                    current_record.revision,
                    current,
                    False,
                )
            if current.transition_count == candidate.transition_count:
                if (
                    current.checkpoint_digest
                    != candidate.checkpoint_digest
                ):
                    raise RecoveryCheckpointConflict(
                        "same session transition count has conflicting checkpoint"
                    )
                return RecoveryCheckpointCommit(
                    stored,
                    current_record.revision,
                    current,
                    False,
                )

            try:
                updated = self.backend.compare_and_swap(
                    self.namespace,
                    head_key,
                    expected_revision=current_record.revision,
                    value=candidate,
                )
                return RecoveryCheckpointCommit(
                    stored,
                    updated.revision,
                    candidate,
                    True,
                )
            except DistributedStateConflict:
                continue

        raise RecoveryCheckpointConflict(
            "recovery checkpoint head CAS retry bound exceeded"
        )

    def current_session(
        self,
        session_id: str,
    ) -> StoredRecoveryCheckpoint | None:
        current = self.head(session_id)
        if current is None:
            return None
        _, head = current
        stored = self.get(head.finalization_id)
        if stored is None:
            raise RuntimeError(
                "recovery checkpoint head references missing item"
            )
        if stored.record.checkpoint.digest != head.checkpoint_digest:
            raise RuntimeError(
                "recovery checkpoint head digest mismatch"
            )
        if stored.record.session_id != session_id:
            raise RuntimeError(
                "recovery checkpoint head item session mismatch"
            )
        return stored

    def require(
        self,
        finalization_id: str,
        *,
        checkpoint_digest: str = "",
    ) -> StoredRecoveryCheckpoint:
        stored = self.get(finalization_id)
        if stored is None:
            raise RecoveryCheckpointConflict(
                "recovery checkpoint is missing"
            )
        if checkpoint_digest and (
            stored.record.checkpoint.digest != checkpoint_digest
        ):
            raise RecoveryCheckpointConflict(
                "recovery checkpoint digest mismatch"
            )
        return stored

    def verify_session_head(
        self,
        session_id: str,
    ) -> bool:
        try:
            stored = self.current_session(session_id)
        except (
            RuntimeError,
            RecoveryCheckpointConflict,
            ValueError,
        ):
            return False
        return stored is not None
