"""Mount 0018.
"""
from __future__ import annotations

MOUNT = "mount_0018"

def ride(rider: str) -> dict:
    if not rider:
        return {"ok": False, "reason": "no_rider"}
    return {"ok": True, "mount": MOUNT, "rider": rider, "speed": 12 + (18 % 8)}
