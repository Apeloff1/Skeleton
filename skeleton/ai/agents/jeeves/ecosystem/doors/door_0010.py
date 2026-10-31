"""Door 0010.
"""
from __future__ import annotations

DOOR = "door_0010"

def open_door(has_key: bool) -> dict:
    if not has_key:
        return {"ok": False, "reason": "locked"}
    return {"ok": True, "door": DOOR, "open": True}
