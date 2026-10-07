"""Distributed single-use execution seal consumption."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.execution_seal import ExecutionSeal, ExecutionSealAuthority
from skeleton.shells.ai.seal_registry import SealReplay, SealUse
from skeleton.shells.ai.store_protocol import VersionedStateBackend


@dataclass(frozen=True)
class DistributedSealConfig:
    namespace: str = "shell-ai-seal-use"


class DistributedExecutionSealRegistry:
    """Use backend put-if-absent as the global replay barrier."""

    def __init__(
        self,
        authority: ExecutionSealAuthority,
        backend: VersionedStateBackend,
        *,
        config: DistributedSealConfig | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.authority = authority
        self.backend = backend
        self.config = config or DistributedSealConfig()
        self._clock = clock

    def consume(
        self,
        seal: ExecutionSeal,
        *,
        principal: str,
        session_id: str,
        plan_pin,
        preconditions_digest: str = "",
        approval_id: str = "",
        release_evidence_digest: str = "",
        assurance_digest: str = "",
    ) -> SealUse:
        self.authority.verify(
            seal,
            principal=principal,
            session_id=session_id,
            plan_pin=plan_pin,
            preconditions_digest=preconditions_digest,
            approval_id=approval_id,
            release_evidence_digest=release_evidence_digest,
            assurance_digest=assurance_digest,
        )
        use = SealUse(
            seal.seal_id,
            principal,
            session_id,
            self._clock(),
        )
        try:
            self.backend.put_if_absent(
                self.config.namespace,
                seal.seal_id,
                use,
            )
        except DistributedStateConflict as exc:
            raise SealReplay("execution seal already consumed globally") from exc
        return use

    def used(self, seal_id: str) -> bool:
        return self.backend.get(self.config.namespace, seal_id) is not None
