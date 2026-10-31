"""Item prime 0351.
"""
from __future__ import annotations

ID = "item_prime_0351"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 351, "tier": 351 % 5}

def apply(context: str = "") -> dict:
    if not context and 351 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
