"""Mount 0007.
"""
from __future__ import annotations

MOUNT = "mount_0007"

def ride(rider: str) -> dict:
    if not rider:
        return {"ok": False, "reason": "no_rider"}
    return {"ok": True, "mount": MOUNT, "rider": rider, "speed": 12 + (7 % 8)}
