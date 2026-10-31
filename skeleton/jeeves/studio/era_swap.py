"""Era swap.
Swaps era abilities and scale.
"""
from typing import Any, Dict

class EraSwap:
    def swap(self, target: str, optical: float) -> Dict[str, Any]:
        if not isinstance(target, str) or not target.strip():
            return {"ok": False, "reason": "empty_target", "schema": "skeleton.era.swap.v1"}
        abilities = ["move", "interact", "salvage"]
        if target in ["ash", "crystal", "void"]:
            abilities += ["optical_attune", "phase_shift"]
        return {"ok": True, "era": target, "abilities": abilities, "scale": round(1.0 + optical*0.1, 2), "optical": optical, "reason": "ok", "schema": "skeleton.era.swap.v1"}
