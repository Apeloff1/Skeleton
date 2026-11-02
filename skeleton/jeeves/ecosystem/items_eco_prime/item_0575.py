"""Item eco_prime 0575.
"""
from __future__ import annotations

ID = "item_eco_prime_0575"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 575, "tier": 575 % 5}

def apply(context: str = "") -> dict:
    if not context and 575 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
