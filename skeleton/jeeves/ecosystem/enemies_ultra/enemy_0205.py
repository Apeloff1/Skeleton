"""Enemy ultra 0205.
"""
from __future__ import annotations

ID = "enemy_ultra_0205"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 205, "tier": 205 % 5}

def apply(context: str = "") -> dict:
    if not context and 205 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
