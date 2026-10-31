"""HUD element 0009.
"""
from __future__ import annotations

ELEMENT = "hud_0009"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
