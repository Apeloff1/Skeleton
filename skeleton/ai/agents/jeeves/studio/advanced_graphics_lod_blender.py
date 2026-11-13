"""Blend LOD with optical weight for advanced graphics."""
from __future__ import annotations
from typing import Dict, Any

def blend_lod(distance: float, optical: float) -> Dict[str, Any]:
    if distance < 0 or optical < 0.7:
        return {"ok": False, "reason": "bad_input", "lod": 2}
    lod = 0 if distance < 15 else 1 if distance < 40 else 2
    return {"ok": True, "lod": lod, "distance": distance, "optical": optical, "reason": "ok"}
