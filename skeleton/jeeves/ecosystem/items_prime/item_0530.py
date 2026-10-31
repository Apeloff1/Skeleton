"""Item prime 0530.
"""
from __future__ import annotations

ID = "item_prime_0530"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 530, "tier": 530 % 5}

def apply(context: str = "") -> dict:
    if not context and 530 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
