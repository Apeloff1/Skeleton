"""Character prime 0484.
"""
from __future__ import annotations

ID = "character_prime_0484"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 484, "tier": 484 % 5}

def apply(context: str = "") -> dict:
    if not context and 484 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
