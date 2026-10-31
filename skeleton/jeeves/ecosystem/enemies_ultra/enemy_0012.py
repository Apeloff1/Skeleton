"""Enemy ultra 0012.
"""
from __future__ import annotations

ID = "enemy_ultra_0012"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 12, "tier": 12 % 5}

def apply(context: str = "") -> dict:
    if not context and 12 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
