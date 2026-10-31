"""HUD element 0038.
"""
from __future__ import annotations

ELEMENT = "hud_0038"

def render(value: float) -> dict:
    return {"ok": True, "element": ELEMENT, "value": value, "visible": True}
