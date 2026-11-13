"""Switch 0001.
"""
from __future__ import annotations

SWITCH = "switch_0001"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
