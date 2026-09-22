"""Memory admission boundary for assurance-approved state transitions.

Keeps persistence decisions separate from execution and ensures only validated
assurance events can cross into durable state handling.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class MemoryAdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class MemoryDecision:
    admitted: bool
    reason: str
    state: str


class MemoryAdmissionGuard:
    """Small deterministic guard before durable memory writes."""

    ALLOWED = {"ACCEPTED"}

    def evaluate(self, event: Mapping[str, Any]) -> MemoryDecision:
        state = str(event.get("state", "")).upper()
        digest = event.get("evidence_digest")
        task_id = event.get("task_id")

        if state not in self.ALLOWED:
            return MemoryDecision(False, "assurance state not accepted", state)

        if not task_id:
            return MemoryDecision(False, "missing task identity", state)

        if not digest:
            return MemoryDecision(False, "missing evidence digest", state)

        return MemoryDecision(True, "validated assurance event", state)


def admit_memory(event: Mapping[str, Any]) -> MemoryDecision:
    return MemoryAdmissionGuard().evaluate(event)
