"""HUD element 0007.
"""
from __future__ import annotations

ELEMENT = "hud_0007"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
