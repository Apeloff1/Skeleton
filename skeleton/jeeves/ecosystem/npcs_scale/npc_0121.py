"""Npc scale 0121.
"""
from __future__ import annotations

ID = "npc_scale_0121"

def describe() -> dict:
    return {"id": ID, "kind": "npc", "tier": 121 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
