"""Projectile scale 0021.
"""
from __future__ import annotations

ID = "projectile_scale_0021"

def describe() -> dict:
    return {"id": ID, "kind": "projectile", "power": 5 + (21 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
