"""Bind visual palette to era."""
from __future__ import annotations
from typing import Dict, Any

def bind_visual(era: str) -> Dict[str, Any]:
    if not era:
        return {"ok": False, "reason": "empty_era", "palette": "#000"}
    palette = "#4a3a2a" if "ash" in era else "#2a4a3a" if "crystal" in era else "#2a2a4a"
    return {"ok": True, "era": era, "palette": palette, "reason": "ok"}
