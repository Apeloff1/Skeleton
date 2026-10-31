"""Mount 0010.
"""
from __future__ import annotations

MOUNT = "mount_0010"

def ride(rider: str) -> dict:
    if not rider:
        return {"ok": False, "reason": "no_rider"}
    return {"ok": True, "mount": MOUNT, "rider": rider, "speed": 12 + (10 % 8)}
