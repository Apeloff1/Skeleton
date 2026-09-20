"""Replay guard for assurance events.

Provides a small deterministic boundary preventing duplicate assurance
transitions from entering downstream state consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable


@dataclass(frozen=True)
class ReplayDecision:
    accepted: bool
    event_key: str
    reason: str


class AssuranceReplayGuard:
    def __init__(self, seed: Iterable[str] | None = None) -> None:
        self._seen: set[str] = set(seed or ())

    @staticmethod
    def key(*, task_id: str, evidence_digest: str, state: str) -> str:
        payload = f"{task_id}:{evidence_digest}:{state}".encode("utf-8")
        return sha256(payload).hexdigest()

    def admit(self, *, task_id: str, evidence_digest: str, state: str) -> ReplayDecision:
        if not task_id or not evidence_digest:
            return ReplayDecision(False, "", "missing_identity")

        event_key = self.key(
            task_id=task_id,
            evidence_digest=evidence_digest,
            state=state,
        )

        if event_key in self._seen:
            return ReplayDecision(False, event_key, "duplicate")

        self._seen.add(event_key)
        return ReplayDecision(True, event_key, "accepted")

    def size(self) -> int:
        return len(self._seen)
