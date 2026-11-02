"""Item eco_prime 0066.
"""
from __future__ import annotations

ID = "item_eco_prime_0066"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 66, "tier": 66 % 5}

def apply(context: str = "") -> dict:
    if not context and 66 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
