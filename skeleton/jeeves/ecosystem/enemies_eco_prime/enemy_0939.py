"""Enemy eco_prime 0939.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0939"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 939, "tier": 939 % 5}

def apply(context: str = "") -> dict:
    if not context and 939 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
