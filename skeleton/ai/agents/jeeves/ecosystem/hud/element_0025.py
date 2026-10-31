"""HUD element 0025.
"""
from __future__ import annotations

ELEMENT = "hud_0025"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
