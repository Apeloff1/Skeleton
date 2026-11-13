"""Mount 0021.
"""
from __future__ import annotations

MOUNT = "mount_0021"

def ride(rider: str) -> dict:
    if not rider:
        return {"ok": False, "reason": "no_rider"}
    return {"ok": True, "mount": MOUNT, "rider": rider, "speed": 12 + (21 % 8)}
