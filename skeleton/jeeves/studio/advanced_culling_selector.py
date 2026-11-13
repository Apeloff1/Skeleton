"""Select cull by distance and optical."""
from __future__ import annotations
from typing import Dict, Any

def select_cull(distance: float, optical: float) -> Dict[str, Any]:
    if distance < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "cull": True}
    cull = distance > 50 * optical
    return {"ok": True, "distance": distance, "cull": cull, "optical": optical, "reason": "ok"}
