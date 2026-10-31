"""Character prime 0494.
"""
from __future__ import annotations

ID = "character_prime_0494"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 494, "tier": 494 % 5}

def apply(context: str = "") -> dict:
    if not context and 494 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
