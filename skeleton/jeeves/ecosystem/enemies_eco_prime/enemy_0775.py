"""Enemy eco_prime 0775.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0775"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 775, "tier": 775 % 5}

def apply(context: str = "") -> dict:
    if not context and 775 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
