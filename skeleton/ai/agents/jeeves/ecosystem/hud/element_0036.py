"""HUD element 0036.
"""
from __future__ import annotations

ELEMENT = "hud_0036"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
