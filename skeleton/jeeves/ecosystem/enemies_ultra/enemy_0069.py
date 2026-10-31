"""Enemy ultra 0069.
"""
from __future__ import annotations

ID = "enemy_ultra_0069"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 69, "tier": 69 % 5}

def apply(context: str = "") -> dict:
    if not context and 69 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
