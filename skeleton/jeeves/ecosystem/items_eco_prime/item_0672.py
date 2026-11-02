"""Item eco_prime 0672.
"""
from __future__ import annotations

ID = "item_eco_prime_0672"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 672, "tier": 672 % 5}

def apply(context: str = "") -> dict:
    if not context and 672 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
