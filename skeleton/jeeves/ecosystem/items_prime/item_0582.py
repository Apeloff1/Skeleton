"""Item prime 0582.
"""
from __future__ import annotations

ID = "item_prime_0582"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 582, "tier": 582 % 5}

def apply(context: str = "") -> dict:
    if not context and 582 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
