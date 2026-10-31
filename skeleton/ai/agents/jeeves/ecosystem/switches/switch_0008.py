"""Switch 0008.
"""
from __future__ import annotations

SWITCH = "switch_0008"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
