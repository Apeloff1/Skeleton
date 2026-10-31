"""HUD element 0013.
"""
from __future__ import annotations

ELEMENT = "hud_0013"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
