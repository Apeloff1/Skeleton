"""Enemy eco_prime 0463.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0463"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 463, "tier": 463 % 5}

def apply(context: str = "") -> dict:
    if not context and 463 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
