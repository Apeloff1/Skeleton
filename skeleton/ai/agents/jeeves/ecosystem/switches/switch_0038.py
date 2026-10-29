"""Switch 0038.
"""
from __future__ import annotations

SWITCH = "switch_0038"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
