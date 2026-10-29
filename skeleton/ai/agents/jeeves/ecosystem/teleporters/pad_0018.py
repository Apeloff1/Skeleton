"""Teleporter 0018.
"""
from __future__ import annotations

PAD = "pad_0018"

def warp(target_room: str) -> dict:
    if not target_room:
        return {"ok": False, "reason": "no_room"}
    return {"ok": True, "pad": PAD, "room": target_room}
