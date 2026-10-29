"""Mount 0039.
"""
from __future__ import annotations

MOUNT = "mount_0039"

def ride(rider: str) -> dict:
    if not rider:
        return {"ok": False, "reason": "no_rider"}
    return {"ok": True, "mount": MOUNT, "rider": rider, "speed": 12 + (39 % 8)}
