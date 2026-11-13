"""Switch 0026.
"""
from __future__ import annotations

SWITCH = "switch_0026"

def toggle(state: bool) -> dict:
    return {"ok": True, "switch": SWITCH, "state": not state}
