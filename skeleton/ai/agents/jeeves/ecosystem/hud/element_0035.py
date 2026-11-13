"""HUD element 0035.
"""
from __future__ import annotations

ELEMENT = "hud_0035"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
