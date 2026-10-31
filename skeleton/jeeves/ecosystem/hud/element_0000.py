"""HUD element 0000.
"""
from __future__ import annotations

ELEMENT = "hud_0000"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
