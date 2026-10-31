"""Character prime 0569.
"""
from __future__ import annotations

ID = "character_prime_0569"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 569, "tier": 569 % 5}

def apply(context: str = "") -> dict:
    if not context and 569 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
