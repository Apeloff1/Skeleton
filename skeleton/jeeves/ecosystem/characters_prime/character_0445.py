"""Character prime 0445.
"""
from __future__ import annotations

ID = "character_prime_0445"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 445, "tier": 445 % 5}

def apply(context: str = "") -> dict:
    if not context and 445 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
