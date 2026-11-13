"""Fidelity gate.
Fail-closed on fidelity floor.
"""
from typing import Any, Dict

class FidelityGate:
    def check(self, fidelity: float, floor: float = 0.92) -> Dict[str, Any]:
        if not isinstance(fidelity, (int, float)) or not isinstance(floor, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.fidelity.gate.v1"}
        ok = fidelity >= floor
        return {"ok": ok, "fidelity": fidelity, "floor": floor, "reason": "ok" if ok else "below_floor", "schema": "skeleton.fidelity.gate.v1"}
