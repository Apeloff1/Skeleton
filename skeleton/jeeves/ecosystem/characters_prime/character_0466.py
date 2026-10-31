"""Character prime 0466.
"""
from __future__ import annotations

ID = "character_prime_0466"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 466, "tier": 466 % 5}

def apply(context: str = "") -> dict:
    if not context and 466 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
