"""HUD element 0014.
"""
from __future__ import annotations

ELEMENT = "hud_0014"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
