"""Enemy mega 0122.
"""
from __future__ import annotations

ID = "enemy_mega_0122"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 122, "tier": 122 % 5}

def apply(context: str = "") -> dict:
    if not context and 122 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
