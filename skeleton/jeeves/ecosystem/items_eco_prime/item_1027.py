"""Item eco_prime 1027.
"""
from __future__ import annotations

ID = "item_eco_prime_1027"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1027, "tier": 1027 % 5}

def apply(context: str = "") -> dict:
    if not context and 1027 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
