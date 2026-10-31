"""Switch 0011.
"""
from __future__ import annotations

SWITCH = "switch_0011"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
