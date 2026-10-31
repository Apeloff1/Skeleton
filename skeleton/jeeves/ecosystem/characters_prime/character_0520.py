"""Character prime 0520.
"""
from __future__ import annotations

ID = "character_prime_0520"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 520, "tier": 520 % 5}

def apply(context: str = "") -> dict:
    if not context and 520 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
