"""HUD element 0006.
"""
from __future__ import annotations

ELEMENT = "hud_0006"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
