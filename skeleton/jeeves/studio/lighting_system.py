"""Lighting system.
Optical intensity and era palette.
"""
from typing import Any, Dict

class LightingSystem:
    def light(self, optical: float, era: str) -> Dict[str, Any]:
        if not isinstance(era, str) or not era.strip():
            return {"ok": False, "reason": "empty_era", "schema": "skeleton.light.v1"}
        intensity = round(0.5 + optical*0.5, 2)
        palette = "#3a2a1a" if era == "ash" else "#2a2a3a"
        return {"ok": True, "intensity": intensity, "palette": palette, "era": era, "optical": optical, "reason": "ok", "schema": "skeleton.light.v1"}
