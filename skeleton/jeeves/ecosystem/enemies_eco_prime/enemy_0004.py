"""Enemy eco_prime 0004.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0004"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 4, "tier": 4 % 5}

def apply(context: str = "") -> dict:
    if not context and 4 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
