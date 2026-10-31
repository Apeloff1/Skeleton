"""Switch 0006.
"""
from __future__ import annotations

SWITCH = "switch_0006"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
