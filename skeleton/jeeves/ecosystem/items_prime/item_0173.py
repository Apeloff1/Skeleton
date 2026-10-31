"""Item prime 0173.
"""
from __future__ import annotations

ID = "item_prime_0173"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 173, "tier": 173 % 5}

def apply(context: str = "") -> dict:
    if not context and 173 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
