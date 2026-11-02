"""Enemy eco_prime 0504.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0504"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 504, "tier": 504 % 5}

def apply(context: str = "") -> dict:
    if not context and 504 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
