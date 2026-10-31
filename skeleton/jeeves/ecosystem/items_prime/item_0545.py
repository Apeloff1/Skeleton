"""Item prime 0545.
"""
from __future__ import annotations

ID = "item_prime_0545"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 545, "tier": 545 % 5}

def apply(context: str = "") -> dict:
    if not context and 545 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
