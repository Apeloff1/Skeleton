"""HUD element 0044.
"""
from __future__ import annotations

ELEMENT = "hud_0044"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
