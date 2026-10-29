"""HUD element 0020.
"""
from __future__ import annotations

ELEMENT = "hud_0020"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
