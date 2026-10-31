"""HUD element 0027.
"""
from __future__ import annotations

ELEMENT = "hud_0027"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
