"""All-in visual era palette."""
from __future__ import annotations
from typing import Dict, Any

def visual_allin(era: str) -> Dict[str, Any]:
    if not era:
        return {"ok": False, "reason": "empty_era", "palette": "#000000"}
    palette = "#6a5a4a" if "ash" in era else "#4a6a5a" if "crystal" in era else "#4a4a6a"
    return {"ok": True, "era": era, "palette": palette, "reason": "ok"}
