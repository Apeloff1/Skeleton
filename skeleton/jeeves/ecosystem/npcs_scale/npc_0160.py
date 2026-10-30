"""Npc scale 0160.
"""
from __future__ import annotations

ID = "npc_scale_0160"

def describe() -> dict:
    return {"id": ID, "kind": "npc", "tier": 160 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
