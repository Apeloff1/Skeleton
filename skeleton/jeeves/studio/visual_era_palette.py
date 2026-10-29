"""Return visual palette by era."""
from __future__ import annotations
from typing import Dict, Any

def get_palette(era: str) -> Dict[str, Any]:
    if not era:
        return {"ok": False, "reason": "empty_era", "palette": "#000000"}
    palette = "#5a4a3a" if "ash" in era else "#3a5a4a" if "crystal" in era else "#3a3a5a"
    return {"ok": True, "era": era, "palette": palette, "reason": "ok"}
