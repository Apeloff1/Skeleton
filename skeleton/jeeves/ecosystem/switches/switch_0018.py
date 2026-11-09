"""Switch 0018.
"""
from __future__ import annotations

SWITCH = "switch_0018"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
