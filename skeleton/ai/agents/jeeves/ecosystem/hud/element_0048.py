"""HUD element 0048.
"""
from __future__ import annotations

ELEMENT = "hud_0048"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
