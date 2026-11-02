"""Item eco_prime 0744.
"""
from __future__ import annotations

ID = "item_eco_prime_0744"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 744, "tier": 744 % 5}

def apply(context: str = "") -> dict:
    if not context and 744 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
