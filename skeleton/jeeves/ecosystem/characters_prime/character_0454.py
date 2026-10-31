"""Character prime 0454.
"""
from __future__ import annotations

ID = "character_prime_0454"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 454, "tier": 454 % 5}

def apply(context: str = "") -> dict:
    if not context and 454 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
