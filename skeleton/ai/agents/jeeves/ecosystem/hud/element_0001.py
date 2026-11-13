"""HUD element 0001.
"""
from __future__ import annotations

ELEMENT = "hud_0001"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
