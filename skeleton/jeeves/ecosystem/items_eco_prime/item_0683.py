"""Item eco_prime 0683.
"""
from __future__ import annotations

ID = "item_eco_prime_0683"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 683, "tier": 683 % 5}

def apply(context: str = "") -> dict:
    if not context and 683 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
