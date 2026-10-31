"""Enemy ultra 0224.
"""
from __future__ import annotations

ID = "enemy_ultra_0224"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 224, "tier": 224 % 5}

def apply(context: str = "") -> dict:
    if not context and 224 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
