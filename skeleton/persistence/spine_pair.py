"""Compare two ledger digests. Does not append and does not advance a fence."""

from __future__ import annotations

from typing import Any

from skeleton.persistence.spine_ledger import SpineLedger


class SpinePairError(RuntimeError):
    """Pair read rejected its inputs. Not a maturity signal."""


class SpinePair:
    """Read the latest digest twice and report equality."""

    def __init__(self, ledger: SpineLedger) -> None:
        if not isinstance(ledger, SpineLedger):
            raise SpinePairError("ledger must be a SpineLedger")
        self.ledger = ledger

    def read(self, *, tenant_id: str, operation_id: str) -> dict[str, Any]:
        first = self.ledger.digest.read(tenant_id=tenant_id, operation_id=operation_id)
        second = self.ledger.digest.read(tenant_id=tenant_id, operation_id=operation_id)
        return {
            "kind": "spine_pair",
            "hit": first["digest"] == second["digest"],
            "law": "digest-equality",
            "citation": "VOL-134",
            "equal": first["digest"] == second["digest"],
            "count": self.ledger.count(tenant_id=tenant_id, operation_id=operation_id),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
