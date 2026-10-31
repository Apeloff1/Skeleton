"""Character prime 0535.
"""
from __future__ import annotations

ID = "character_prime_0535"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 535, "tier": 535 % 5}

def apply(context: str = "") -> dict:
    if not context and 535 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
