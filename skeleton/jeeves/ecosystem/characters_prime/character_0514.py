"""Character prime 0514.
"""
from __future__ import annotations

ID = "character_prime_0514"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 514, "tier": 514 % 5}

def apply(context: str = "") -> dict:
    if not context and 514 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
