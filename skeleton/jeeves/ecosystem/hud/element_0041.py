"""HUD element 0041.
"""
from __future__ import annotations

ELEMENT = "hud_0041"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
