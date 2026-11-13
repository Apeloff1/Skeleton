"""Mode projector.
Maps graphics mode to projection and layers.
"""
from typing import Any, Dict

class ModeProjector:
    def project(self, mode: str) -> Dict[str, Any]:
        if mode not in ["2d", "2.5d", "2.9d", "3d", "4d"]:
            return {"ok": False, "reason": "bad_mode", "schema": "skeleton.mode.proj.v1"}
        proj = "orthographic" if mode in ["2d", "2.5d"] else "perspective"
        layers = 1 if mode == "2d" else 2 if mode == "2.5d" else 3
        return {"ok": True, "mode": mode, "projection": proj, "layers": layers, "reason": "ok", "schema": "skeleton.mode.proj.v1"}
