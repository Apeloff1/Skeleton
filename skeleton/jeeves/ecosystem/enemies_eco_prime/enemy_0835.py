"""Enemy eco_prime 0835.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0835"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 835, "tier": 835 % 5}

def apply(context: str = "") -> dict:
    if not context and 835 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
