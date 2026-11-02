"""Item eco_prime 0907.
"""
from __future__ import annotations

ID = "item_eco_prime_0907"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 907, "tier": 907 % 5}

def apply(context: str = "") -> dict:
    if not context and 907 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
