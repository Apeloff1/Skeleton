"""Adjust scale up/down by era."""
from __future__ import annotations
from typing import Dict, Any

def adjust_scale(era: str, base: float) -> Dict[str, Any]:
    if not era or base <= 0:
        return {"ok": False, "reason": "bad_input", "scale": 1.0}
    scale = base * 1.2 if era in ("N64", "PS1", "PS2") else base * 0.8 if era in ("NES", "GB") else base
    return {"ok": True, "era": era, "scale": scale, "reason": "ok"}
