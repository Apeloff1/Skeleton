"""HUD element 0047.
"""
from __future__ import annotations

ELEMENT = "hud_0047"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
