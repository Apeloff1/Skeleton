"""Blend advanced graphics with optical."""
from __future__ import annotations
from typing import Dict, Any

def blend_graphics(lod: int, optical: float) -> Dict[str, Any]:
    if lod < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "blended": False}
    return {"ok": True, "lod": lod, "optical": optical, "blended": True, "reason": "ok"}
