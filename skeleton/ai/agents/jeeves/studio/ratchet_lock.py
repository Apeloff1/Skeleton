"""Ratchet lock.
High-water mark lock for fidelity.
"""
from typing import Any, Dict

class RatchetLock:
    def lock(self, fidelity: float, high_water: float) -> Dict[str, Any]:
        if not isinstance(fidelity, (int, float)) or not isinstance(high_water, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.ratchet.lock.v1"}
        locked = fidelity >= high_water
        return {"ok": True, "fidelity": fidelity, "high_water": high_water, "locked": locked, "reason": "ok" if locked else "below_water", "schema": "skeleton.ratchet.lock.v1"}
