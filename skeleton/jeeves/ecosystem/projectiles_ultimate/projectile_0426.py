"""Projectile ultimate 0426.
"""
from __future__ import annotations

ID = "projectile_ultimate_0426"

def describe() -> dict:
    return {"id": ID, "kind": "projectile", "power": 5 + (426 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
