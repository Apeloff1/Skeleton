"""Npc scale 0157.
"""
from __future__ import annotations

ID = "npc_scale_0157"

def describe() -> dict:
    return {"id": ID, "kind": "npc", "tier": 157 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
