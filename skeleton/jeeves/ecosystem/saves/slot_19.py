"""Save slot 19.
"""
from __future__ import annotations

SLOT = 19

def write_slot(state: dict) -> dict:
    if not isinstance(state, dict) or not state:
        return {"ok": False, "reason": "empty_state"}
    return {"ok": True, "slot": SLOT, "keys": sorted(state.keys())[:12]}

def read_slot() -> dict:
    return {"ok": True, "slot": SLOT, "empty": False}
