"""Era-aware game engine.
Supports era swap, era-consistent abilities, and upscale/downscale adjustments.
"""
from typing import Any, Dict, List

GAMING_ERAS = ["nes", "snes", "gb", "gbc", "gba", "n64", "ps1", "ps2", "dreamcast", "arcade"]
SKELETON_ERAS = ["ash", "crystal", "void", "rift", "core", "ember", "ice", "prism"]

class EraEngine:
    def __init__(self, era: str = "ash"):
        self.era = era if era in GAMING_ERAS + SKELETON_ERAS else "ash"
        self.scale = 1.0
        self.abilities = self._abilities_for(self.era)

    def _abilities_for(self, era: str) -> List[str]:
        base = ["move", "interact", "salvage"]
        if era in GAMING_ERAS:
            base.extend(["jump", "shoot"])
        if era in ["ps1", "ps2", "n64"]:
            base.append("3d_move")
        if era in SKELETON_ERAS:
            base.extend(["optical_attune", "phase_shift"])
        return base

    def swap_era(self, new_era: str) -> Dict[str, Any]:
        if new_era not in GAMING_ERAS + SKELETON_ERAS:
            return {"ok": False, "reason": "unknown era"}
        old = self.era
        self.era = new_era
        self.abilities = self._abilities_for(new_era)
        return {"ok": True, "from": old, "to": new_era, "abilities": self.abilities}

    def upscale(self, factor: float = 1.5) -> Dict[str, Any]:
        self.scale = min(4.0, self.scale * factor)
        return {"scale": self.scale, "resolution_hint": int(256 * self.scale)}

    def downscale(self, factor: float = 0.75) -> Dict[str, Any]:
        self.scale = max(0.25, self.scale * factor)
        return {"scale": self.scale, "resolution_hint": int(256 * self.scale)}

    def consistent_ability(self, ability: str) -> bool:
        return ability in self.abilities

    def status(self) -> Dict[str, Any]:
        return {
            "era": self.era,
            "scale": self.scale,
            "abilities": self.abilities,
            "gaming": self.era in GAMING_ERAS,
            "schema": "skeleton.era_engine.v1",
        }
