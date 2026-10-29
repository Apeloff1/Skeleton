"""Switch 0013.
"""
from __future__ import annotations

SWITCH = "switch_0013"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
