"""Enemy eco_prime 0601.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0601"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 601, "tier": 601 % 5}

def apply(context: str = "") -> dict:
    if not context and 601 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
