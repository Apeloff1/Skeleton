"""Result envelope for sealed execution with committed recovery/audit evidence."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.durable_readiness import DurableEvidenceReadinessReport
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
    durable_readiness: DurableEvidenceReadinessReport | None = None
    post_execution_maintenance_error: str = ""

    def __post_init__(self) -> None:
        if len(self.post_execution_maintenance_error) > 512:
            raise ValueError(
                "post_execution_maintenance_error too long"
            )

    @property
    def post_execution_maintenance_ok(self) -> bool:
        return (
            not self.post_execution_maintenance_error
            and (
                self.durable_readiness is None
                or self.durable_readiness.ready
            )
        )

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
            "durable_readiness": (
                None
                if self.durable_readiness is None
                else self.durable_readiness.to_dict()
            ),
            "post_execution_maintenance_ok": (
                self.post_execution_maintenance_ok
            ),
            "post_execution_maintenance_error": (
                self.post_execution_maintenance_error
            ),
        }
