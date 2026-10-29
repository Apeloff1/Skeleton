"""HUD element 0045.
"""
from __future__ import annotations

ELEMENT = "hud_0045"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
