"""Enemy eco_prime 0623.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0623"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 623, "tier": 623 % 5}

def apply(context: str = "") -> dict:
    if not context and 623 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
