"""Composable assurance pipeline boundary.

Keeps validation stages explicit and deterministic before runtime consumers
receive state-changing events.
"""

from __future__ import annotations

from dataclasses import dataclass

from .assurance_replay_guard import AssuranceReplayGuard


@dataclass(frozen=True)
class PipelineResult:
    accepted: bool
    reason: str


class AssurancePipeline:
    def __init__(self, replay_guard: AssuranceReplayGuard | None = None) -> None:
        self.replay_guard = replay_guard or AssuranceReplayGuard()

    def check(self, *, task_id: str, evidence_digest: str, state: str) -> PipelineResult:
        decision = self.replay_guard.admit(
            task_id=task_id,
            evidence_digest=evidence_digest,
            state=state,
        )

        return PipelineResult(
            accepted=decision.accepted,
            reason=decision.reason,
        )
