"""Item prime 0598.
"""
from __future__ import annotations

ID = "item_prime_0598"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 598, "tier": 598 % 5}

def apply(context: str = "") -> dict:
    if not context and 598 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
