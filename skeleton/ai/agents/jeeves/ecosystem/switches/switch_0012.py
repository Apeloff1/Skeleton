"""Switch 0012.
"""
from __future__ import annotations

SWITCH = "switch_0012"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
