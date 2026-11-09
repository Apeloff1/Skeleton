"""HUD element 0002.
"""
from __future__ import annotations

ELEMENT = "hud_0002"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
