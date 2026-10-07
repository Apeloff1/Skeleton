"""Cut gate in front of any spine switch.

A switch is refused. Drift miss or chain mismatch is recorded. The fence is
not advanced.
"""

from __future__ import annotations

from typing import Any


class SpineCutGateError(RuntimeError):
    """Cut gate rejected its inputs. Not a maturity signal."""


class SpineCutGate:
    """Refuse the switch. Record why."""

    def consider(self, cutover: dict[str, Any], chain: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(cutover, dict) or not isinstance(chain, dict):
            raise SpineCutGateError("cutover and chain must be cards")
        reasons: list[str] = []
        if cutover.get("hit") is not True:
            reasons.append("cutover-miss")
        if chain.get("match") is not True:
            reasons.append("chain-mismatch")
        if cutover.get("applied", 0) != 0:
            reasons.append("apply-open")
        return {
            "kind": "spine_cut_gate",
            "hit": False,
            "law": "switch-refused",
            "citation": "VOL-134",
            "switched": False,
            "reasons": reasons or ["switch-not-landed"],
            "applied_fence": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
