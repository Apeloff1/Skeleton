"""HUD element 0016.
"""
from __future__ import annotations

ELEMENT = "hud_0016"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
