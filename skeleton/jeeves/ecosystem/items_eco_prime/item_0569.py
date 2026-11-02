"""Item eco_prime 0569.
"""
from __future__ import annotations

ID = "item_eco_prime_0569"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 569, "tier": 569 % 5}

def apply(context: str = "") -> dict:
    if not context and 569 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
