"""HUD element 0028.
"""
from __future__ import annotations

ELEMENT = "hud_0028"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
