"""Npc scale 0169.
"""
from __future__ import annotations

ID = "npc_scale_0169"

def describe() -> dict:
    return {"id": ID, "kind": "npc", "tier": 169 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
