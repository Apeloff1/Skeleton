"""Switch 0004.
"""
from __future__ import annotations

SWITCH = "switch_0004"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
