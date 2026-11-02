"""Item eco_prime 0806.
"""
from __future__ import annotations

ID = "item_eco_prime_0806"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 806, "tier": 806 % 5}

def apply(context: str = "") -> dict:
    if not context and 806 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
