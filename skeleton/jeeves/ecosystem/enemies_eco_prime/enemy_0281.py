"""Enemy eco_prime 0281.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0281"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 281, "tier": 281 % 5}

def apply(context: str = "") -> dict:
    if not context and 281 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
