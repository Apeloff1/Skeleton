"""Camera rig 0033.
"""
from __future__ import annotations

RIG = "rig_0033"

def follow(target: str, distance: float = 5.0) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "rig": RIG, "target": target, "distance": max(1.0, distance)}
