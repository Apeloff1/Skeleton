"""Explicit apply gate for a repair intent.

The gate records that a caller asked to apply. It does not accept a delivery
and it does not advance a fence. applied stays 0 until a later seam exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from skeleton.persistence.spine_repair import RepairIntent


class SpineApplyError(RuntimeError):
    """Apply gate rejected its inputs. Not a maturity signal."""


@dataclass(frozen=True, slots=True)
class ApplyRefusal:
    outbox_id: str
    reason: str
    refused_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "outbox_id": self.outbox_id,
            "reason": self.reason,
            "refused_at": self.refused_at.isoformat(),
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
        }


class SpineApplyGate:
    """Refuse every intent. The fence is not a side effect of this call."""

    def __init__(self) -> None:
        self.refusals: list[ApplyRefusal] = []

    def consider(self, intent: RepairIntent, *, now: datetime | None = None) -> ApplyRefusal:
        if not isinstance(intent, RepairIntent):
            raise SpineApplyError("intent must be a RepairIntent")
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineApplyError("now must be timezone-aware")
        refusal = ApplyRefusal(intent.outbox_id, "apply-not-landed", instant)
        self.refusals.append(refusal)
        return refusal

    def card(self) -> dict[str, Any]:
        return {
            "kind": "spine_apply_gate",
            "hit": True,
            "law": "apply-refuses-until-landed",
            "citation": "VOL-134",
            "refused": len(self.refusals),
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
