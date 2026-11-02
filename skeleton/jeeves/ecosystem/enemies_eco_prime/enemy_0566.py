"""Enemy eco_prime 0566.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0566"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 566, "tier": 566 % 5}

def apply(context: str = "") -> dict:
    if not context and 566 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
