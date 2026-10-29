"""Mount 0038.
"""
from __future__ import annotations

MOUNT = "mount_0038"

def ride(rider: str) -> dict:
    if not rider:
        return {"ok": False, "reason": "no_rider"}
    return {"ok": True, "mount": MOUNT, "rider": rider, "speed": 12 + (38 % 8)}
