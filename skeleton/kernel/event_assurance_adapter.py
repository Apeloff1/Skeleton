"""Assurance adapter for kernel event dispatch.

Keeps assurance checks at the event boundary without replacing EventBus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from skeleton.kernel.assurance import AssuranceEnvelope


@dataclass(frozen=True)
class AssuranceDispatchResult:
    accepted: bool
    reason: str = ""


class EventAssuranceAdapter:
    """Small boundary object for validating events before consumers handle them."""

    def validate(self, envelope: AssuranceEnvelope) -> AssuranceDispatchResult:
        if not envelope.task_id:
            return AssuranceDispatchResult(False, "missing_task_identity")
        if not envelope.digest:
            return AssuranceDispatchResult(False, "missing_digest")
        return AssuranceDispatchResult(True)

    def attach_metadata(self, payload: Dict[str, Any], envelope: AssuranceEnvelope) -> Dict[str, Any]:
        enriched = dict(payload)
        enriched["assurance"] = {
            "task_id": envelope.task_id,
            "digest": envelope.digest,
            "state": envelope.state.value,
        }
        return enriched
