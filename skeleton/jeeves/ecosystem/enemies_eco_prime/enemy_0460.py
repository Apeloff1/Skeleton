"""Enemy eco_prime 0460.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0460"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 460, "tier": 460 % 5}

def apply(context: str = "") -> dict:
    if not context and 460 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
