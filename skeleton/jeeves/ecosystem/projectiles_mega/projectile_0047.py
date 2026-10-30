"""Projectile mega 0047.
"""
from __future__ import annotations

ID = "projectile_mega_0047"

def describe() -> dict:
    return {"id": ID, "kind": "projectile", "power": 5 + (47 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
