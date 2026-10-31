"""Switch 0023.
"""
from __future__ import annotations

SWITCH = "switch_0023"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
