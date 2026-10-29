"""HUD element 0040.
"""
from __future__ import annotations

ELEMENT = "hud_0040"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
