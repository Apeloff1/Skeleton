"""Witness card for the landed P2 spine reads.

Bundles lag, catalog, and status. It does not dispatch and it does not sign off.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.spine_catalog import SpineCatalog
from skeleton.persistence.spine_lag import SpineLag
from skeleton.persistence.spine_status import SpineStatus


class SpineWitnessError(RuntimeError):
    """Witness rejected its inputs. Not a maturity signal."""


class SpineWitness:
    """One card over lag, catalog, and status."""

    def __init__(self, lag: SpineLag, catalog: SpineCatalog, status: SpineStatus) -> None:
        if not isinstance(lag, SpineLag):
            raise SpineWitnessError("lag must be a SpineLag")
        if not isinstance(catalog, SpineCatalog):
            raise SpineWitnessError("catalog must be a SpineCatalog")
        if not isinstance(status, SpineStatus):
            raise SpineWitnessError("status must be a SpineStatus")
        self.lag = lag
        self.catalog = catalog
        self.status = status

    def card(self, *, tenant_id: str, operation_id: str) -> dict[str, Any]:
        lag = self.lag.read(operation_id=operation_id)
        catalog = self.catalog.card(tenant_id=tenant_id)
        status = self.status.card(tenant_id=tenant_id, resource_id=f"op:{operation_id}")
        return {
            "kind": "spine_witness",
            "hit": lag["pending"] == 0 and status["poison_count"] == 0,
            "law": "lag-catalog-status",
            "citation": "VOL-134",
            "pending": lag["pending"],
            "published": lag["published"],
            "catalog_count": catalog["count"],
            "fence_epoch": status["fence_epoch"],
            "poison_count": status["poison_count"],
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
