"""Item eco_prime 0875.
"""
from __future__ import annotations

ID = "item_eco_prime_0875"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 875, "tier": 875 % 5}

def apply(context: str = "") -> dict:
    if not context and 875 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
