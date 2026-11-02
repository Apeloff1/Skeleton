"""Item eco_prime 1113.
"""
from __future__ import annotations

ID = "item_eco_prime_1113"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1113, "tier": 1113 % 5}

def apply(context: str = "") -> dict:
    if not context and 1113 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
