"""Deep advanced graphics render."""
from __future__ import annotations
from typing import Dict, Any

def render_deep(lod: int, optical: float) -> Dict[str, Any]:
    if lod < 0 or optical < 0.7:
        return {"ok": False, "reason": "floors", "rendered": False}
    return {"ok": True, "lod": lod, "optical": optical, "rendered": True, "reason": "ok"}
