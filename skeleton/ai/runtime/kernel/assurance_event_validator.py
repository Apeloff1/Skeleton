"""Assurance validation boundary for kernel events.

Keeps assurance checks separate from transport while allowing EventBus
consumers to validate event envelopes deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from skeleton.kernel.assurance import AssuranceEnvelope, AssuranceState


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str = ""


class AssuranceEventValidator:
    """Validate assurance metadata before runtime consumers act."""

    def validate(self, envelope: AssuranceEnvelope) -> ValidationResult:
        if not envelope.task_id:
            return ValidationResult(False, "missing_task_identity")

        if not envelope.digest:
            return ValidationResult(False, "missing_digest")

        if envelope.state == AssuranceState.ACCEPTED and not envelope.source:
            return ValidationResult(False, "accepted_requires_source")

        return ValidationResult(True, "ok")

    def validate_payload(self, payload: Dict[str, Any]) -> ValidationResult:
        task_id = payload.get("task_id")
        digest = payload.get("assurance_digest")

        if not task_id:
            return ValidationResult(False, "missing_task_identity")
        if not digest:
            return ValidationResult(False, "missing_digest")
        return ValidationResult(True, "ok")
