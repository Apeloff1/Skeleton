"""Repair plan for poison marks.

A plan records the intent to repair. It does not accept a delivery and it does
not advance a fence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.spine_projection import PoisonMark
from skeleton.persistence.spine_quarantine import SpineQuarantine


class SpineRepairError(RuntimeError):
    """Repair plan rejected its inputs. Not a maturity signal."""


@dataclass(frozen=True, slots=True)
class RepairIntent:
    outbox_id: str
    tenant_id: str
    reason: str
    planned_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "outbox_id": self.outbox_id,
            "tenant_id": self.tenant_id,
            "reason": self.reason,
            "planned_at": self.planned_at.isoformat(),
            "stored_prose": 0,
            "completion_checkbox": False,
        }


class SpineRepairPlan:
    """Turn quarantine marks into intents. Does not apply them."""

    def __init__(self, quarantine: SpineQuarantine) -> None:
        if not isinstance(quarantine, SpineQuarantine):
            raise SpineRepairError("quarantine must be a SpineQuarantine")
        self.quarantine = quarantine
        self.intents: list[RepairIntent] = []

    def plan(self, *, tenant_id: str, now: datetime | None = None) -> tuple[RepairIntent, ...]:
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRepairError("now must be timezone-aware")
        marks: tuple[PoisonMark, ...] = self.quarantine.list(tenant_id=tenant_id)
        planned = tuple(
            RepairIntent(mark.outbox_id, mark.tenant_id, mark.reason, instant) for mark in marks
        )
        self.intents.extend(planned)
        return planned

    def card(self, tenant_id: str) -> dict[str, Any]:
        return {
            "kind": "spine_repair_plan",
            "hit": True,
            "law": "plan-does-not-apply",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "planned": len(self.intents),
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
