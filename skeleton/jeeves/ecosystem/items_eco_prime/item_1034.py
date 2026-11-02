"""Item eco_prime 1034.
"""
from __future__ import annotations

ID = "item_eco_prime_1034"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1034, "tier": 1034 % 5}

def apply(context: str = "") -> dict:
    if not context and 1034 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
