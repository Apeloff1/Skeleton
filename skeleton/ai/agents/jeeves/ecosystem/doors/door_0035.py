"""Door 0035.
"""
from __future__ import annotations

DOOR = "door_0035"

def open_door(has_key: bool) -> dict:
    if not has_key:
        return {"ok": False, "reason": "locked"}
    return {"ok": True, "door": DOOR, "open": True}
