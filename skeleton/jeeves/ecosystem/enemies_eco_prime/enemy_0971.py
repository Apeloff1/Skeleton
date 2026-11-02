"""Enemy eco_prime 0971.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0971"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 971, "tier": 971 % 5}

def apply(context: str = "") -> dict:
    if not context and 971 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
