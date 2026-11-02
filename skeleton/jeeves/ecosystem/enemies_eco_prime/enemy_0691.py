"""Enemy eco_prime 0691.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0691"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 691, "tier": 691 % 5}

def apply(context: str = "") -> dict:
    if not context and 691 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
