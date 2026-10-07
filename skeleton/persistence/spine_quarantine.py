"""Poison quarantine for the P2 spine.

Lists marks for one tenant. Does not repair them and does not advance the fence.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.spine_depth import SpineProjection
from skeleton.persistence.spine_projection import PoisonMark


class SpineQuarantineError(RuntimeError):
    """Quarantine input cannot be read. Not a maturity signal."""


class SpineQuarantine:
    """Tenant-scoped poison list. Read only."""

    def __init__(self, projection: SpineProjection) -> None:
        if not isinstance(projection, SpineProjection):
            raise SpineQuarantineError("projection must be a SpineProjection")
        self.projection = projection

    def list(self, *, tenant_id: str) -> tuple[PoisonMark, ...]:
        if not isinstance(tenant_id, str) or not tenant_id.strip() or tenant_id != tenant_id.strip():
            raise SpineQuarantineError("tenant_id must be canonical text")
        if not hasattr(self.projection, "poisons"):
            raise SpineQuarantineError("projection has no poison read")
        return tuple(mark for mark in self.projection.poisons() if mark.tenant_id == tenant_id)

    def card(self, tenant_id: str) -> dict[str, Any]:
        marks = self.list(tenant_id=tenant_id)
        return {
            "kind": "spine_quarantine",
            "hit": len(marks) == 0,
            "law": "poison-read-only",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "count": len(marks),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
