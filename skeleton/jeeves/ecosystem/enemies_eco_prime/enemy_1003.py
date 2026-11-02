"""Enemy eco_prime 1003.
"""
from __future__ import annotations

ID = "enemy_eco_prime_1003"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1003, "tier": 1003 % 5}

def apply(context: str = "") -> dict:
    if not context and 1003 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
