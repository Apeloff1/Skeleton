"""Enemy eco_prime 1018.
"""
from __future__ import annotations

ID = "enemy_eco_prime_1018"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1018, "tier": 1018 % 5}

def apply(context: str = "") -> dict:
    if not context and 1018 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
