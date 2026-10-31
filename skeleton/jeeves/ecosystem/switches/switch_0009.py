"""Switch 0009.
"""
from __future__ import annotations

SWITCH = "switch_0009"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
