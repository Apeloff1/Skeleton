"""Item eco_prime 0741.
"""
from __future__ import annotations

ID = "item_eco_prime_0741"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 741, "tier": 741 % 5}

def apply(context: str = "") -> dict:
    if not context and 741 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
