"""Item eco_prime 1168.
"""
from __future__ import annotations

ID = "item_eco_prime_1168"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1168, "tier": 1168 % 5}

def apply(context: str = "") -> dict:
    if not context and 1168 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
