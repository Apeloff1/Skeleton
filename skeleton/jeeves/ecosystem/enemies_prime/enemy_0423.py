"""Enemy prime 0423.
"""
from __future__ import annotations

ID = "enemy_prime_0423"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 423, "tier": 423 % 5}

def apply(context: str = "") -> dict:
    if not context and 423 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
