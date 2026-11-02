"""Item eco_prime 0223.
"""
from __future__ import annotations

ID = "item_eco_prime_0223"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 223, "tier": 223 % 5}

def apply(context: str = "") -> dict:
    if not context and 223 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
