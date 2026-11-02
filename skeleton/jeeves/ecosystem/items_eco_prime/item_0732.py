"""Item eco_prime 0732.
"""
from __future__ import annotations

ID = "item_eco_prime_0732"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 732, "tier": 732 % 5}

def apply(context: str = "") -> dict:
    if not context and 732 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
