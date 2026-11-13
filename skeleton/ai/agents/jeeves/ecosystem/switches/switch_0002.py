"""Switch 0002.
"""
from __future__ import annotations

SWITCH = "switch_0002"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
