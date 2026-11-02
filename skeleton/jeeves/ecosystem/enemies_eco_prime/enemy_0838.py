"""Enemy eco_prime 0838.
"""
from __future__ import annotations

ID = "enemy_eco_prime_0838"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 838, "tier": 838 % 5}

def apply(context: str = "") -> dict:
    if not context and 838 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
