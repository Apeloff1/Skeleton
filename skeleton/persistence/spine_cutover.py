"""Cutover card for the P2 spine.

Reads lag, drift, and the apply gate. It does not dispatch, does not advance
a fence, and does not claim cutover is complete.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.spine_apply import SpineApplyGate
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_lag import SpineLag


class SpineCutoverError(RuntimeError):
    """Cutover read rejected its inputs. Not a maturity signal."""


class SpineCutover:
    """Bundle the reads an operator needs before any later cut."""

    def __init__(self, lag: SpineLag, drift: SpineDrift, gate: SpineApplyGate) -> None:
        if not isinstance(lag, SpineLag):
            raise SpineCutoverError("lag must be a SpineLag")
        if not isinstance(drift, SpineDrift):
            raise SpineCutoverError("drift must be a SpineDrift")
        if not isinstance(gate, SpineApplyGate):
            raise SpineCutoverError("gate must be a SpineApplyGate")
        self.lag = lag
        self.drift = drift
        self.gate = gate

    def card(self, *, tenant_id: str, operation_id: str) -> dict[str, Any]:
        lag = self.lag.read(operation_id=operation_id)
        drift = self.drift.read(tenant_id=tenant_id, resource_id=f"op:{operation_id}")
        gate = self.gate.card()
        return {
            "kind": "spine_cutover",
            "hit": lag["pending"] == 0 and drift["hit"] is True and gate["applied"] == 0,
            "law": "read-before-cut",
            "citation": "VOL-134",
            "pending": lag["pending"],
            "published": lag["published"],
            "sqlite_epoch": drift["sqlite_epoch"],
            "mongo_epoch": drift["mongo_epoch"],
            "apply_refused": gate["applied"] == 0,
            "apply_refusal_count": gate["refused"],
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
