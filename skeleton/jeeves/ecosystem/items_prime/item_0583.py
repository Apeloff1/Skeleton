"""Item prime 0583.
"""
from __future__ import annotations

ID = "item_prime_0583"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 583, "tier": 583 % 5}

def apply(context: str = "") -> dict:
    if not context and 583 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
