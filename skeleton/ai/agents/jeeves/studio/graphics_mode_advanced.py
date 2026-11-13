"""Advanced graphics mode with 2D-4D projection flags."""
from __future__ import annotations
from typing import Dict, Any

def project_mode(mode: str, optical: float) -> Dict[str, Any]:
    if optical < 0.7:
        return {"ok": False, "reason": "optical_floor", "mode": mode}
    layers = 1 if mode == "2d" else 2 if mode == "2.5d" else 3 if mode == "3d" else 4
    return {"ok": True, "mode": mode, "layers": layers, "time_axis": mode == "4d", "projection": "orthographic", "reason": "ok"}
