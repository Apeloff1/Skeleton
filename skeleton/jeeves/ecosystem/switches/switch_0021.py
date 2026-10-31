"""Switch 0021.
"""
from __future__ import annotations

SWITCH = "switch_0021"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
