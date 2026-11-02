"""Enemy eco_prime 0638.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0638"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 638, "tier": 638 % 5}

def apply(context: str = "") -> dict:
    if not context and 638 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
