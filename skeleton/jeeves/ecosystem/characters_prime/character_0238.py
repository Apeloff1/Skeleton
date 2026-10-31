"""Character prime 0238.
"""
from __future__ import annotations

ID = "character_prime_0238"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 238, "tier": 238 % 5}

def apply(context: str = "") -> dict:
    if not context and 238 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
