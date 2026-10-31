"""Item prime 0570.
"""
from __future__ import annotations

ID = "item_prime_0570"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 570, "tier": 570 % 5}

def apply(context: str = "") -> dict:
    if not context and 570 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
