"""Tenant sweep of fence drift.

Reads epochs for a bounded resource list. Does not advance either fence.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.spine_drift import SpineDrift


class SpineSweepError(RuntimeError):
    """Sweep rejected its inputs. Not a maturity signal."""


class SpineSweep:
    """Compare a bounded set of resources for one tenant."""

    def __init__(self, drift: SpineDrift, *, max_resources: int = 32) -> None:
        if not isinstance(drift, SpineDrift):
            raise SpineSweepError("drift must be a SpineDrift")
        if isinstance(max_resources, bool) or not isinstance(max_resources, int) or not 1 <= max_resources <= 256:
            raise SpineSweepError("max_resources must be an integer from 1 to 256")
        self.drift = drift
        self.max_resources = max_resources

    def read(self, *, tenant_id: str, resource_ids: tuple[str, ...] | list[str]) -> dict[str, Any]:
        if not isinstance(resource_ids, (tuple, list)):
            raise SpineSweepError("resource_ids must be a sequence")
        if len(resource_ids) > self.max_resources:
            raise SpineSweepError("resource_ids exceeds max_resources")
        rows = [self.drift.read(tenant_id=tenant_id, resource_id=resource_id) for resource_id in resource_ids]
        mismatched = sum(1 for row in rows if not row["hit"])
        return {
            "kind": "spine_sweep",
            "hit": mismatched == 0,
            "law": "bounded-drift-sweep",
            "citation": "VOL-132",
            "tenant_id": tenant_id,
            "scanned": len(rows),
            "mismatched": mismatched,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
