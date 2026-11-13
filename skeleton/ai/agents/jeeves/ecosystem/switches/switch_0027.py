"""Switch 0027.
"""
from __future__ import annotations

SWITCH = "switch_0027"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
