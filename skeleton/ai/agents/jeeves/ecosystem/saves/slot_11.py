"""Save slot 11.
"""
from __future__ import annotations

SLOT = 11

def write_slot(state: dict) -> dict:
    if not isinstance(state, dict) or not state:
        return {"ok": False, "reason": "empty_state"}
    return {"ok": True, "slot": SLOT, "keys": sorted(state.keys())[:12]}

def read_slot() -> dict:
    return {"ok": True, "slot": SLOT, "empty": False}
