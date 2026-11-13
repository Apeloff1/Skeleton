"""HUD element 0023.
"""
from __future__ import annotations

ELEMENT = "hud_0023"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
