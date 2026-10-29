"""Advanced era graphics binder.
Mode consistency, scale hints, and ability sets across gaming and Skeleton eras.
"""
from typing import Any, Dict

class EraGraphicsBinder:
    def bind(self, era: str, optical: float, scale: float = 1.0) -> Dict[str, Any]:
        if era in ["nes", "gb", "gbc"]:
            mode, layers = "2d", 1
        elif era in ["snes", "gba"]:
            mode, layers = "2.5d", 2
        elif era in ["n64", "ps1"]:
            mode, layers = "2.9d", 6
        elif era in ["ps2", "dreamcast"]:
            mode, layers = "3d", 8
        else:
            mode, layers = "2.5d", 2
        abilities = ["move", "interact", "salvage"]
        if era in ["nes", "snes", "gb", "gbc", "gba", "n64", "ps1", "ps2", "dreamcast", "arcade"]:
            abilities.extend(["jump", "shoot"])
        if era in ["ash", "crystal", "void", "rift", "core", "ember", "ice", "prism"]:
            abilities.extend(["optical_attune", "phase_shift"])
        return {
            "era": era,
            "mode": mode,
            "layers": layers,
            "abilities": abilities,
            "scale": scale,
            "optical": optical,
            "respray": True,
            "schema": "skeleton.era.graphics.v2",
        }
