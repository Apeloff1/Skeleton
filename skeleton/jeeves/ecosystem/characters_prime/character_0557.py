"""Character prime 0557.
"""
from __future__ import annotations

ID = "character_prime_0557"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 557, "tier": 557 % 5}

def apply(context: str = "") -> dict:
    if not context and 557 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
