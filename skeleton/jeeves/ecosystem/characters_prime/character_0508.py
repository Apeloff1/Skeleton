"""Character prime 0508.
"""
from __future__ import annotations

ID = "character_prime_0508"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 508, "tier": 508 % 5}

def apply(context: str = "") -> dict:
    if not context and 508 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
