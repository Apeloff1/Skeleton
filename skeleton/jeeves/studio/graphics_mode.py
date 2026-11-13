"""Graphics mode.
2D to 4D with projection and layers.
"""
from typing import Any, Dict

class GraphicsMode:
    def set(self, mode: str) -> Dict[str, Any]:
        if mode not in ["2d", "2.5d", "2.9d", "3d", "4d"]:
            return {"ok": False, "reason": "bad_mode", "schema": "skeleton.gfx.mode.v1"}
        proj = "orthographic" if mode in ["2d", "2.5d"] else "perspective"
        layers = 1 if mode == "2d" else 2 if mode == "2.5d" else 3
        time = mode == "4d"
        return {"ok": True, "mode": mode, "projection": proj, "layers": layers, "time_axis": time, "reason": "ok", "schema": "skeleton.gfx.mode.v1"}
