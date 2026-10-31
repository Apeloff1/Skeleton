"""Character prime 0055.
"""
from __future__ import annotations

ID = "character_prime_0055"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 55, "tier": 55 % 5}

def apply(context: str = "") -> dict:
    if not context and 55 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
