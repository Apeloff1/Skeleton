"""Enemy eco_prime 0599.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0599"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 599, "tier": 599 % 5}

def apply(context: str = "") -> dict:
    if not context and 599 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
