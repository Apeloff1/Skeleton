"""Npc scale 0003.
"""
from __future__ import annotations

ID = "npc_scale_0003"

def describe() -> dict:
    return {"id": ID, "kind": "npc", "tier": 3 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
