"""Graphics modes.
2D, 2.5D through 2.9D, 3D, and 4D rendering bindings for the era engine.
"""
from typing import Any, Dict

class GraphicsModes:
    MODES = {
        "2d": {"projection": "orthographic", "layers": 1, "depth": False, "time_axis": False},
        "2.5d": {"projection": "oblique", "layers": 2, "depth": True, "time_axis": False},
        "2.6d": {"projection": "isometric", "layers": 3, "depth": True, "time_axis": False},
        "2.7d": {"projection": "dimetric", "layers": 4, "depth": True, "time_axis": False},
        "2.8d": {"projection": "trimetric", "layers": 5, "depth": True, "time_axis": False},
        "2.9d": {"projection": "hybrid", "layers": 6, "depth": True, "time_axis": False},
        "3d": {"projection": "perspective", "layers": 8, "depth": True, "time_axis": False},
        "4d": {"projection": "perspective_time", "layers": 8, "depth": True, "time_axis": True},
    }

    def __init__(self, mode: str = "2.5d"):
        self.mode = mode if mode in self.MODES else "2.5d"

    def set_mode(self, mode: str) -> Dict[str, Any]:
        if mode not in self.MODES:
            return {"ok": False, "available": list(self.MODES)}
        self.mode = mode
        return {"ok": True, "mode": mode, **self.MODES[mode]}

    def current(self) -> Dict[str, Any]:
        return {"mode": self.mode, **self.MODES[self.mode]}

    def for_era(self, era: str) -> str:
        if era in ["nes", "gb", "gbc"]:
            return "2d"
        if era in ["snes", "gba"]:
            return "2.5d"
        if era in ["n64", "ps1"]:
            return "2.9d"
        if era in ["ps2", "dreamcast"]:
            return "3d"
        return "2.5d"
