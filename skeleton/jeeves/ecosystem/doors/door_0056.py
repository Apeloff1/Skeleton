"""Door 0056.
"""
from __future__ import annotations

DOOR = "door_0056"

def open_door(has_key: bool) -> dict:
    if not has_key:
        return {"ok": False, "reason": "locked"}
    return {"ok": True, "door": DOOR, "open": True}
