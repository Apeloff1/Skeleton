"""Switch 0028.
"""
from __future__ import annotations

SWITCH = "switch_0028"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
