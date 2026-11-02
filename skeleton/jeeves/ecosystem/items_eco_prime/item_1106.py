"""Item eco_prime 1106.
"""
from __future__ import annotations

ID = "item_eco_prime_1106"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 1106, "tier": 1106 % 5}

def apply(context: str = "") -> dict:
    if not context and 1106 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
