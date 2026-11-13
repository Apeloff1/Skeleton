"""Switch 0015.
"""
from __future__ import annotations

SWITCH = "switch_0015"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
