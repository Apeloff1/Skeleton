"""Character prime 0531.
"""
from __future__ import annotations

ID = "character_prime_0531"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 531, "tier": 531 % 5}

def apply(context: str = "") -> dict:
    if not context and 531 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
