"""Enemy eco_prime 0796.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0796"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 796, "tier": 796 % 5}

def apply(context: str = "") -> dict:
    if not context and 796 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
