"""HUD element 0012.
"""
from __future__ import annotations

ELEMENT = "hud_0012"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
