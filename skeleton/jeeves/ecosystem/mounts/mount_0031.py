"""Mount 0031.
"""
from __future__ import annotations

MOUNT = "mount_0031"

def ride(rider: str) -> dict:
    if not rider:
        return {"ok": False, "reason": "no_rider"}
    return {"ok": True, "mount": MOUNT, "rider": rider, "speed": 12 + (31 % 8)}
