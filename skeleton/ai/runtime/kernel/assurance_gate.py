"""Evidence-bound assurance gate for kernel state transitions.

Keeps validation metadata separate from execution logic. Consumers can use this
as a narrow boundary before durable state changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping


class AssuranceState(str, Enum):
    ACCEPTED = "accepted"
    REVIEW = "review"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AssuranceRecord:
    identity: str
    evidence_hash: str
    state: AssuranceState
    reason: str = ""


def canonical_digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(raw).hexdigest()


class AssuranceGate:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def evaluate(
        self,
        *,
        identity: str,
        evidence: Mapping[str, Any],
        validated: bool,
    ) -> AssuranceRecord:
        digest = canonical_digest(evidence)
        if digest in self._seen:
            return AssuranceRecord(identity, digest, AssuranceState.REJECTED, "replay")

        self._seen.add(digest)

        if not validated:
            return AssuranceRecord(identity, digest, AssuranceState.REVIEW, "validation-required")

        return AssuranceRecord(identity, digest, AssuranceState.ACCEPTED)
