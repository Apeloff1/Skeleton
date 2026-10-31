"""HUD element 0026.
"""
from __future__ import annotations

ELEMENT = "hud_0026"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
