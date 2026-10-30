"""Npc scale 0008.
"""
from __future__ import annotations

ID = "npc_scale_0008"

def describe() -> dict:
    return {"id": ID, "kind": "npc", "tier": 8 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
