"""Item eco_prime 1141.
"""
from __future__ import annotations

ID = "item_eco_prime_1141"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1141, "tier": 1141 % 5}

def apply(context: str = "") -> dict:
    if not context and 1141 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
