"""Switch 0000.
"""
from __future__ import annotations

SWITCH = "switch_0000"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
