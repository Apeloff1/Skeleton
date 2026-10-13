"""Single-use execution seal registry preventing authorization replay."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from skeleton.shells.ai.execution_seal import ExecutionSeal, ExecutionSealAuthority


@dataclass(frozen=True)
class SealUse:
    seal_id: str
    principal: str
    session_id: str
    consumed_at: float

    def to_dict(self) -> dict[str, object]:
        return {
            "seal_id": self.seal_id,
            "principal": self.principal,
            "session_id": self.session_id,
            "consumed_at": self.consumed_at,
        }


class SealReplay(RuntimeError):
    pass


class ExecutionSealRegistry:
    def __init__(
        self,
        authority: ExecutionSealAuthority,
        *,
        max_items: int = 100000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.authority = authority
        self.max_items = max_items
        self._clock = clock
        self._used: dict[str, SealUse] = {}
        self._lock = threading.RLock()

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
        with self._lock:
            if seal.seal_id in self._used:
                raise SealReplay("execution seal already consumed")
            if len(self._used) >= self.max_items:
                raise RuntimeError("execution seal replay registry capacity exhausted")
            item = SealUse(
                seal.seal_id,
                principal,
                session_id,
                self._clock(),
            )
            self._used[seal.seal_id] = item
            return item

    def used(self, seal_id: str) -> bool:
        with self._lock:
            return seal_id in self._used

    def snapshot(self) -> tuple[SealUse, ...]:
        with self._lock:
            return tuple(self._used[key] for key in sorted(self._used))
