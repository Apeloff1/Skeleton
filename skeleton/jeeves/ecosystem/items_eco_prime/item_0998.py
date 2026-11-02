"""Item eco_prime 0998.
"""
from __future__ import annotations

ID = "item_eco_prime_0998"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 998, "tier": 998 % 5}

def apply(context: str = "") -> dict:
    if not context and 998 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
