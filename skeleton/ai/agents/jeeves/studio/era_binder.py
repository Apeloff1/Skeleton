"""Era binder.
Binds era to abilities, scale, and optical.
"""
from typing import Any, Dict

class EraBinder:
    def bind(self, era: str, optical: float) -> Dict[str, Any]:
        if not isinstance(era, str) or not era.strip():
            return {"ok": False, "reason": "empty_era", "schema": "skeleton.era.bind.v1"}
        scale = 1.0 + optical * 0.1
        abilities = ["move", "interact", "salvage"]
        if era in ["ash", "crystal", "void"]:
            abilities += ["optical_attune", "phase_shift"]
        return {"ok": True, "era": era, "scale": round(scale, 2), "abilities": abilities, "optical": optical, "reason": "ok", "schema": "skeleton.era.bind.v1"}
