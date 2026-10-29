"""Era graphics binder.
Binds era engine, graphics modes, and asset respray in one step.
"""
from typing import Any, Dict

class EraGraphicsBinder:
    def bind(self, era: str, optical: float) -> Dict[str, Any]:
        mode = "2d" if era in ["nes", "gb", "gbc"] else "2.5d" if era in ["snes", "gba"] else "2.9d" if era in ["n64", "ps1"] else "3d" if era in ["ps2", "dreamcast"] else "2.5d"
        abilities = ["move", "interact", "salvage"]
        if era in ["nes", "snes", "gb", "gbc", "gba", "n64", "ps1", "ps2", "dreamcast", "arcade"]:
            abilities.extend(["jump", "shoot"])
        if era in ["ash", "crystal", "void", "rift", "core", "ember", "ice", "prism"]:
            abilities.extend(["optical_attune", "phase_shift"])
        return {
            "era": era,
            "mode": mode,
            "abilities": abilities,
            "optical": optical,
            "respray": True,
            "schema": "skeleton.era.graphics.v1",
        }
