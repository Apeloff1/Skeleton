"""Enemy ultra 0218.
"""
from __future__ import annotations

ID = "enemy_ultra_0218"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 218, "tier": 218 % 5}

def apply(context: str = "") -> dict:
    if not context and 218 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
