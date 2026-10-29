"""HUD element 0017.
"""
from __future__ import annotations

ELEMENT = "hud_0017"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
