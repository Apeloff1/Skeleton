"""Enemy ultra 0001.
"""
from __future__ import annotations

ID = "enemy_ultra_0001"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 1, "tier": 1 % 5}

def apply(context: str = "") -> dict:
    if not context and 1 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
