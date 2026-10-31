"""Enemy ultra 0217.
"""
from __future__ import annotations

ID = "enemy_ultra_0217"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 217, "tier": 217 % 5}

def apply(context: str = "") -> dict:
    if not context and 217 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
