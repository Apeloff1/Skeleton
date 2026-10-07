"""Kernel assurance primitives.

A small, deterministic boundary for attaching provenance and validation
metadata to existing runtime events without replacing the EventBus model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


class AssuranceState(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AssuranceEnvelope:
    """Bounded metadata attached to a runtime decision."""

    task_id: str
    source: str
    payload_digest: str
    state: AssuranceState = AssuranceState.PENDING

    @staticmethod
    def digest(payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def create(cls, task_id: str, source: str, payload: Mapping[str, Any]) -> "AssuranceEnvelope":
        return cls(
            task_id=task_id,
            source=source,
            payload_digest=cls.digest(payload),
        )

    def accept(self) -> "AssuranceEnvelope":
        return AssuranceEnvelope(
            task_id=self.task_id,
            source=self.source,
            payload_digest=self.payload_digest,
            state=AssuranceState.ACCEPTED,
        )

    def reject(self) -> "AssuranceEnvelope":
        return AssuranceEnvelope(
            task_id=self.task_id,
            source=self.source,
            payload_digest=self.payload_digest,
            state=AssuranceState.REJECTED,
        )
