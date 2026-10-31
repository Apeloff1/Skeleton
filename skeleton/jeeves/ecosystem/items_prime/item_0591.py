"""Item prime 0591.
"""
from __future__ import annotations

ID = "item_prime_0591"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 591, "tier": 591 % 5}

def apply(context: str = "") -> dict:
    if not context and 591 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
