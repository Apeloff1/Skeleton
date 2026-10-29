"""Switch 0014.
"""
from __future__ import annotations

SWITCH = "switch_0014"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
