"""Unified assurance kernel facade.

Provides one narrow entry point for validated assurance transitions.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssuranceDecision:
    accepted: bool
    state: str
    reason: str


class AssuranceKernelFacade:
    """Coordinates assurance checks without owning execution authority."""

    TERMINAL_STATES = {"ACCEPTED", "REJECTED"}

    def evaluate(self, event: Any) -> AssuranceDecision:
        task_id = getattr(event, "task_id", None)
        digest = getattr(event, "evidence_digest", None)
        state = getattr(event, "state", "REJECTED")

        if not task_id:
            return AssuranceDecision(False, "REJECTED", "missing_task_identity")

        if not digest:
            return AssuranceDecision(False, "REJECTED", "missing_evidence_digest")

        if state not in {"ACCEPTED", "REVIEW", "REJECTED"}:
            return AssuranceDecision(False, "REJECTED", "invalid_state")

        return AssuranceDecision(True, state, "validated")
