"""Character prime 0452.
"""
from __future__ import annotations

ID = "character_prime_0452"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 452, "tier": 452 % 5}

def apply(context: str = "") -> dict:
    if not context and 452 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
