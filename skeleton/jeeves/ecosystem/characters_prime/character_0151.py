"""Character prime 0151.
"""
from __future__ import annotations

ID = "character_prime_0151"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 151, "tier": 151 % 5}

def apply(context: str = "") -> dict:
    if not context and 151 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
