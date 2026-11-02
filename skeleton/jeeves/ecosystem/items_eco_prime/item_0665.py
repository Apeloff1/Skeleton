"""Item eco_prime 0665.
"""
from __future__ import annotations

ID = "item_eco_prime_0665"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 665, "tier": 665 % 5}

def apply(context: str = "") -> dict:
    if not context and 665 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
