"""Item eco_prime 0858.
"""
from __future__ import annotations

ID = "item_eco_prime_0858"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 858, "tier": 858 % 5}

def apply(context: str = "") -> dict:
    if not context and 858 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
