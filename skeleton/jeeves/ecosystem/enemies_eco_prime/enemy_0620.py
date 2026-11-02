"""Enemy eco_prime 0620.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0620"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 620, "tier": 620 % 5}

def apply(context: str = "") -> dict:
    if not context and 620 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
