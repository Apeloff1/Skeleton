"""Enemy eco_prime 0770.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0770"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 770, "tier": 770 % 5}

def apply(context: str = "") -> dict:
    if not context and 770 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
