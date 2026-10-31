"""Bind era to graphics palette."""
from __future__ import annotations
from typing import Dict, Any

def bind_palette(era: str) -> Dict[str, Any]:
    if not era:
        return {"ok": False, "reason": "empty_era", "palette": "#000000"}
    palette = "#3a2a1a" if era == "ash" else "#2a3a2a" if era == "crystal" else "#1a1a3a"
    return {"ok": True, "era": era, "palette": palette, "reason": "ok"}
