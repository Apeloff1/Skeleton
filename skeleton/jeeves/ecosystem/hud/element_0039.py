"""HUD element 0039.
"""
from __future__ import annotations

ELEMENT = "hud_0039"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
