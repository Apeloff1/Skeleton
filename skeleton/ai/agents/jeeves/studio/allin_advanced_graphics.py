"""All-in advanced graphics with LOD and optical."""
from __future__ import annotations
from typing import Dict, Any

def graphics_allin(distance: float, optical: float) -> Dict[str, Any]:
    if distance < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "lod": 2}
    lod = 0 if distance < 18 * optical else 1 if distance < 42 * optical else 2
    return {"ok": True, "lod": lod, "distance": distance, "optical": optical, "reason": "ok"}
