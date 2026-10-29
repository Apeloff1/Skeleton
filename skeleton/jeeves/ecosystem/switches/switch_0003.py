"""Switch 0003.
"""
from __future__ import annotations

SWITCH = "switch_0003"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
