"""Character prime 0523.
"""
from __future__ import annotations

ID = "character_prime_0523"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 523, "tier": 523 % 5}

def apply(context: str = "") -> dict:
    if not context and 523 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
