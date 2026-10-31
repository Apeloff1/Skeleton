"""Item prime 0585.
"""
from __future__ import annotations

ID = "item_prime_0585"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 585, "tier": 585 % 5}

def apply(context: str = "") -> dict:
    if not context and 585 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
