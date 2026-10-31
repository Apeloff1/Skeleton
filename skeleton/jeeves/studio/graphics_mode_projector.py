"""Project graphics mode with era mapping and depth flags."""
from __future__ import annotations
from typing import Dict, Any

def project_mode(mode: str, era: str) -> Dict[str, Any]:
    if mode not in ("2D", "2.5D", "2.6D", "2.7D", "2.8D", "2.9D", "3D", "4D"):
        return {"ok": False, "reason": "bad_mode", "projection": "none"}
    projection = "orthographic" if mode in ("2D", "2.5D", "2.6D") else "perspective"
    time_axis = mode == "4D"
    return {"ok": True, "mode": mode, "era": era, "projection": projection, "time_axis": time_axis, "reason": "ok"}
