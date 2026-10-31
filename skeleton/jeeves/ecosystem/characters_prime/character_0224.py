"""Character prime 0224.
"""
from __future__ import annotations

ID = "character_prime_0224"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 224, "tier": 224 % 5}

def apply(context: str = "") -> dict:
    if not context and 224 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
