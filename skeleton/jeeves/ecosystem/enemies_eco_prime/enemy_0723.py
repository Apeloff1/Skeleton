"""Enemy eco_prime 0723.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0723"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 723, "tier": 723 % 5}

def apply(context: str = "") -> dict:
    if not context and 723 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
