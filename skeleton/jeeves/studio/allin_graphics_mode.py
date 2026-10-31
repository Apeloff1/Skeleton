"""All-in graphics mode projector with era."""
from __future__ import annotations
from typing import Dict, Any

def mode_allin(mode: str, era: str) -> Dict[str, Any]:
    valid = ("2D", "2.5D", "2.6D", "2.7D", "2.8D", "2.9D", "3D", "4D")
    if mode not in valid or not era:
        return {"ok": False, "reason": "bad_input", "projection": "none"}
    projection = "orthographic" if mode in ("2D", "2.5D", "2.6D") else "perspective"
    return {"ok": True, "mode": mode, "era": era, "projection": projection, "time": mode == "4D", "reason": "ok"}
