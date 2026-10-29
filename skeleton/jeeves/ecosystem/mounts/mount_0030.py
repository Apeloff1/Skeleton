"""Mount 0030.
"""
from __future__ import annotations

MOUNT = "mount_0030"

def ride(rider: str) -> dict:
    if not rider:
        return {"ok": False, "reason": "no_rider"}
    return {"ok": True, "mount": MOUNT, "rider": rider, "speed": 12 + (30 % 8)}
