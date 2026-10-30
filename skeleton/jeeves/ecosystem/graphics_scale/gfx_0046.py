"""Graphics scale 0046.
"""
from __future__ import annotations

GFX = "gfx_scale_0046"

def project(mode: str, optical: float = 0.9) -> dict:
    modes = ["2D", "2.5D", "2.9D", "3D", "4D"]
    if mode not in modes:
        return {"ok": False, "reason": "bad_mode"}
    return {"ok": True, "gfx": GFX, "mode": mode, "optical": optical, "lod": int(optical * 4)}
