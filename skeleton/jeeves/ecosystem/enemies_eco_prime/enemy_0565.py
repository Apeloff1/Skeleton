"""Enemy eco_prime 0565.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0565"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 565, "tier": 565 % 5}

def apply(context: str = "") -> dict:
    if not context and 565 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
