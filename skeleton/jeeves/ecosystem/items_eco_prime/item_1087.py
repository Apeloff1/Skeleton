"""Item eco_prime 1087.
"""
from __future__ import annotations

ID = "item_eco_prime_1087"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1087, "tier": 1087 % 5}

def apply(context: str = "") -> dict:
    if not context and 1087 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
