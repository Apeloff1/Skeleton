"""Npc scale 0061.
"""
from __future__ import annotations

ID = "npc_scale_0061"

def describe() -> dict:
    return {"id": ID, "kind": "npc", "tier": 61 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
