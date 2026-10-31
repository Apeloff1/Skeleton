"""Item prime 0562.
"""
from __future__ import annotations

ID = "item_prime_0562"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 562, "tier": 562 % 5}

def apply(context: str = "") -> dict:
    if not context and 562 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
