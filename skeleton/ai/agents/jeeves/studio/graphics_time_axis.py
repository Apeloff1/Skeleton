"""Flag time axis for 4D mode."""
from __future__ import annotations
from typing import Dict, Any

def set_time_axis(mode: str) -> Dict[str, Any]:
    if mode not in ("2D", "2.5D", "2.6D", "2.7D", "2.8D", "2.9D", "3D", "4D"):
        return {"ok": False, "reason": "bad_mode", "time": False}
    return {"ok": True, "mode": mode, "time": mode == "4D", "reason": "ok"}
