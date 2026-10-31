"""Character prime 0525.
"""
from __future__ import annotations

ID = "character_prime_0525"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 525, "tier": 525 % 5}

def apply(context: str = "") -> dict:
    if not context and 525 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
