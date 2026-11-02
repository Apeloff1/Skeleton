"""Enemy eco_prime 0416.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0416"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 416, "tier": 416 % 5}

def apply(context: str = "") -> dict:
    if not context and 416 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
