"""Switch 0025.
"""
from __future__ import annotations

SWITCH = "switch_0025"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
