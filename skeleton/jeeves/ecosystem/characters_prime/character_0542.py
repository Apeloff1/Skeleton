"""Character prime 0542.
"""
from __future__ import annotations

ID = "character_prime_0542"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 542, "tier": 542 % 5}

def apply(context: str = "") -> dict:
    if not context and 542 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
