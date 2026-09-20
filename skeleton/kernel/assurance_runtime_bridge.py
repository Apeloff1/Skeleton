"""Runtime bridge for assurance-aware kernel dispatch.

Keeps assurance decisions separate from execution while providing one narrow
boundary for consumers that need validated events.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeDecision:
    accepted: bool
    reason: str
    event_key: str | None = None


class AssuranceRuntimeBridge:
    def __init__(self, validator: Any, replay_guard: Any) -> None:
        self.validator = validator
        self.replay_guard = replay_guard

    def process(self, *, task_id: str, evidence_digest: str, state: str) -> RuntimeDecision:
        if not task_id:
            return RuntimeDecision(False, "missing_identity")
        if not evidence_digest:
            return RuntimeDecision(False, "missing_digest")

        replay = self.replay_guard.admit(
            task_id=task_id,
            evidence_digest=evidence_digest,
            state=state,
        )

        if not replay.accepted:
            return RuntimeDecision(False, replay.reason, replay.event_key)

        return RuntimeDecision(True, "accepted", replay.event_key)
