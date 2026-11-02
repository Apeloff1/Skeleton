"""Character eco_prime 0694.
"""
from __future__ import annotations

ID = "character_eco_prime_0694"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 694, "tier": 694 % 5}

def apply(context: str = "") -> dict:
    if not context and 694 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
