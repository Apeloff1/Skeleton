"""HUD element 0033.
"""
from __future__ import annotations

ELEMENT = "hud_0033"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
