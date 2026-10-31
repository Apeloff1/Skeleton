"""Camera rig 0044.
"""
from __future__ import annotations

RIG = "rig_0044"

def follow(target: str, distance: float = 5.0) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "rig": RIG, "target": target, "distance": max(1.0, distance)}
