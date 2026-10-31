"""Enemy ultra 0157.
"""
from __future__ import annotations

ID = "enemy_ultra_0157"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 157, "tier": 157 % 5}

def apply(context: str = "") -> dict:
    if not context and 157 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
