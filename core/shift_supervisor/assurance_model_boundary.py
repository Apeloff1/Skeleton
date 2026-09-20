from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .assurance_context import AssuranceContext


@dataclass(frozen=True, slots=True)
class ModelBoundaryDecision:
    allowed: bool
    reason: str
    assurance: AssuranceContext


class AssuranceModelBoundary:
    """Small deterministic guard around supervisor model execution.

    The boundary does not call models or alter prompts. It only ensures that
    model requests have provenance before entering the gateway.
    """

    def admit(
        self,
        *,
        actor: str,
        correlation_id: str,
        operation: str,
        payload: dict[str, Any],
    ) -> ModelBoundaryDecision:
        assurance = AssuranceContext.create(
            actor=actor,
            correlation_id=correlation_id,
            operation=operation,
            payload=payload,
        )

        if not assurance.actor.strip():
            return ModelBoundaryDecision(False, "missing_actor", assurance)
        if not assurance.correlation_id.strip():
            return ModelBoundaryDecision(False, "missing_correlation_id", assurance)
        if not assurance.digest:
            return ModelBoundaryDecision(False, "missing_digest", assurance)

        return ModelBoundaryDecision(True, "accepted", assurance)
