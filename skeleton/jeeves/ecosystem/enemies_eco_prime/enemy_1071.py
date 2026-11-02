"""Enemy eco_prime 1071.
"""
from __future__ import annotations

ID = "enemy_eco_prime_1071"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1071, "tier": 1071 % 5}

def apply(context: str = "") -> dict:
    if not context and 1071 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
