"""Item eco_prime 0923.
"""
from __future__ import annotations

ID = "item_eco_prime_0923"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 923, "tier": 923 % 5}

def apply(context: str = "") -> dict:
    if not context and 923 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
