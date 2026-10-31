"""Enemy ultra 0079.
"""
from __future__ import annotations

ID = "enemy_ultra_0079"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 79, "tier": 79 % 5}

def apply(context: str = "") -> dict:
    if not context and 79 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
