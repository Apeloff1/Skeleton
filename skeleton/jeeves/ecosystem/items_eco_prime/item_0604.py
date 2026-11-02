"""Item eco_prime 0604.
"""
from __future__ import annotations

ID = "item_eco_prime_0604"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 604, "tier": 604 % 5}

def apply(context: str = "") -> dict:
    if not context and 604 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
