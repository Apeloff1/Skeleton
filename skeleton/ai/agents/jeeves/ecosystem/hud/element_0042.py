"""HUD element 0042.
"""
from __future__ import annotations

ELEMENT = "hud_0042"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
