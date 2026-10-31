"""Character prime 0536.
"""
from __future__ import annotations

ID = "character_prime_0536"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 536, "tier": 536 % 5}

def apply(context: str = "") -> dict:
    if not context and 536 % 31 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
