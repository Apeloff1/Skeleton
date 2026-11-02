"""Enemy eco_prime 0987.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0987"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 987, "tier": 987 % 5}

def apply(context: str = "") -> dict:
    if not context and 987 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
