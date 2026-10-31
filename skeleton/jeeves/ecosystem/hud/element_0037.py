"""HUD element 0037.
"""
from __future__ import annotations

ELEMENT = "hud_0037"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
