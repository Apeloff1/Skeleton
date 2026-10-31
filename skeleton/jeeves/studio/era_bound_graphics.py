"""Era-bound live graphics.
Era swap updates palette, mode, and abilities live.
"""
from typing import Any, Dict

class EraBoundGraphics:
    def __init__(self):
        self.era = "ash"
        self.mode = "2.5d"
        self.palette = "#3a2a1a"

    def swap(self, era: str) -> Dict[str, Any]:
        self.era = era
        if era in ["ps2", "dreamcast"]:
            self.mode = "3d"
            self.palette = "#2a2a3a"
        elif era in ["n64", "ps1"]:
            self.mode = "2.9d"
            self.palette = "#1a2a3a"
        else:
            self.mode = "2.5d"
            self.palette = "#3a2a1a"
        return {"era": self.era, "mode": self.mode, "palette": self.palette, "schema": "skeleton.era.bound.v1"}
