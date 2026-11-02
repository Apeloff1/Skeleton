"""Item eco_prime 0403.
"""
from __future__ import annotations

ID = "item_eco_prime_0403"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 403, "tier": 403 % 5}

def apply(context: str = "") -> dict:
    if not context and 403 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
