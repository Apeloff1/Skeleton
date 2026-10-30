"""Projectile scale 0090.
"""
from __future__ import annotations

ID = "projectile_scale_0090"

def describe() -> dict:
    return {"id": ID, "kind": "projectile", "power": 5 + (90 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
