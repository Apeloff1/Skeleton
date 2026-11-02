"""Item eco_prime 0970.
"""
from __future__ import annotations

ID = "item_eco_prime_0970"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 970, "tier": 970 % 5}

def apply(context: str = "") -> dict:
    if not context and 970 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
