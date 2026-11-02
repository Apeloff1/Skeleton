"""Enemy eco_prime 0574.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0574"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 574, "tier": 574 % 5}

def apply(context: str = "") -> dict:
    if not context and 574 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
