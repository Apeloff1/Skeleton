"""HUD element 0005.
"""
from __future__ import annotations

ELEMENT = "hud_0005"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
