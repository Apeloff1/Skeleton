"""Door 0031.
"""
from __future__ import annotations

DOOR = "door_0031"

def open_door(has_key: bool) -> dict:
    if not has_key:
        return {"ok": False, "reason": "locked"}
    return {"ok": True, "door": DOOR, "open": True}
