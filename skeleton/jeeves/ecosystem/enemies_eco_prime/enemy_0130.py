"""Enemy eco_prime 0130.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0130"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 130, "tier": 130 % 5}

def apply(context: str = "") -> dict:
    if not context and 130 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
