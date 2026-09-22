"""Distributed AI session checkpoint store over a CAS backend."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.session_store import AISessionConflict, StoredAISession
from skeleton.shells.ai.store_protocol import VersionedStateBackend


@dataclass(frozen=True)
class DistributedSessionConfig:
    namespace: str = "shell-ai-session"


class DistributedAISessionStore:
    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        config: DistributedSessionConfig | None = None,
    ) -> None:
        self.backend = backend
        self.config = config or DistributedSessionConfig()

    def put(
        self,
        checkpoint: AISessionCheckpoint,
        *,
        expected_revision: int | None = None,
    ) -> StoredAISession:
        current = self.backend.get(self.config.namespace, checkpoint.session_id)
        if current is None:
            if expected_revision not in {None, 0}:
                raise AISessionConflict("distributed AI session does not exist")
            try:
                record = self.backend.put_if_absent(
                    self.config.namespace,
                    checkpoint.session_id,
                    checkpoint,
                )
            except DistributedStateConflict as exc:
                raise AISessionConflict("distributed AI session create conflict") from exc
            return StoredAISession(
                checkpoint.session_id,
                record.revision,
                checkpoint,
            )
        if not isinstance(current.value, AISessionCheckpoint):
            raise RuntimeError("distributed AI session record type mismatch")
        if current.value.digest == checkpoint.digest:
            return StoredAISession(
                checkpoint.session_id,
                current.revision,
                current.value,
            )
        if expected_revision is not None and current.revision != expected_revision:
            raise AISessionConflict("distributed AI session revision conflict")
        try:
            record = self.backend.compare_and_swap(
                self.config.namespace,
                checkpoint.session_id,
                expected_revision=current.revision,
                value=checkpoint,
            )
        except DistributedStateConflict as exc:
            raise AISessionConflict("distributed AI session CAS conflict") from exc
        return StoredAISession(
            checkpoint.session_id,
            record.revision,
            checkpoint,
        )

    def current(self, session_id: str) -> StoredAISession:
        record = self.backend.get(self.config.namespace, session_id)
        if record is None or not isinstance(record.value, AISessionCheckpoint):
            raise KeyError(session_id)
        return StoredAISession(
            session_id,
            record.revision,
            record.value,
        )
