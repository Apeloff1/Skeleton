"""Character eco_prime 0874.
"""
from __future__ import annotations

ID = "character_eco_prime_0874"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 874, "tier": 874 % 5}

def apply(context: str = "") -> dict:
    if not context and 874 % 59 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
