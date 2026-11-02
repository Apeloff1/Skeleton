"""Item eco_prime 0969.
"""
from __future__ import annotations

ID = "item_eco_prime_0969"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 969, "tier": 969 % 5}

def apply(context: str = "") -> dict:
    if not context and 969 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
