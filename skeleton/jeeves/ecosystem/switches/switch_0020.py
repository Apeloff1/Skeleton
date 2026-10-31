"""Switch 0020.
"""
from __future__ import annotations

SWITCH = "switch_0020"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
