"""Result envelope for sealed execution with committed recovery/audit evidence."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.evidence_finalizer import FinalizedAIExecutionEvidence
from skeleton.shells.ai.execution_attempt import AIExecutionAttempt
from skeleton.shells.ai.orchestrator import AIExecutionBundle
from skeleton.shells.ai.preconditions import PreconditionReport
from skeleton.shells.ai.seal_registry import SealUse


@dataclass(frozen=True)
class AISealedFinalizedExecution:
    execution: AIExecutionBundle
    preconditions: PreconditionReport | None
    seal_use: SealUse
    finalized: FinalizedAIExecutionEvidence
    execution_attempt: AIExecutionAttempt | None = None

    @property
    def ok(self) -> bool:
        return (
            self.execution.ok
            and self.finalized.recovery_checkpoint.session.phase
            in {"complete", "failed"}
            and (
                self.execution_attempt is None
                or self.execution_attempt.terminal
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "execution": self.execution.to_dict(),
            "preconditions": (
                None
                if self.preconditions is None
                else self.preconditions.to_dict()
            ),
            "seal_use": self.seal_use.to_dict(),
            "finalized": self.finalized.to_dict(),
            "execution_attempt": (
                None
                if self.execution_attempt is None
                else self.execution_attempt.to_dict()
            ),
        }
