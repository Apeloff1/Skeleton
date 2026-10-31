"""Item prime 0592.
"""
from __future__ import annotations

ID = "item_prime_0592"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 592, "tier": 592 % 5}

def apply(context: str = "") -> dict:
    if not context and 592 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
