"""Enemy ultra 0100.
"""
from __future__ import annotations

ID = "enemy_ultra_0100"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 100, "tier": 100 % 5}

def apply(context: str = "") -> dict:
    if not context and 100 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
