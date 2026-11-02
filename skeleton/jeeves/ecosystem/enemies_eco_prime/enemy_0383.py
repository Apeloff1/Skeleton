"""Enemy eco_prime 0383.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0383"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 383, "tier": 383 % 5}

def apply(context: str = "") -> dict:
    if not context and 383 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
