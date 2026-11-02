"""Enemy eco_prime 1041.
"""
from __future__ import annotations

ID = "enemy_eco_prime_1041"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1041, "tier": 1041 % 5}

def apply(context: str = "") -> dict:
    if not context and 1041 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
