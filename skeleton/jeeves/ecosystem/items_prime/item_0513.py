"""Item prime 0513.
"""
from __future__ import annotations

ID = "item_prime_0513"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 513, "tier": 513 % 5}

def apply(context: str = "") -> dict:
    if not context and 513 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
