"""Achievement pack 012.
"""
from __future__ import annotations

PACK = "ach_012"

def unlock(progress: float) -> dict:
    if progress < 0 or progress > 1:
        return {"ok": False, "reason": "bad_progress"}
    unlocked = progress >= 0.9
    return {"ok": True, "pack": PACK, "unlocked": unlocked, "progress": progress}
