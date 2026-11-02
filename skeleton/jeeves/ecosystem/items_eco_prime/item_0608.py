"""Item eco_prime 0608.
"""
from __future__ import annotations

ID = "item_eco_prime_0608"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 608, "tier": 608 % 5}

def apply(context: str = "") -> dict:
    if not context and 608 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
