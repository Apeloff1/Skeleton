"""Enemy ultra 0035.
"""
from __future__ import annotations

ID = "enemy_ultra_0035"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 35, "tier": 35 % 5}

def apply(context: str = "") -> dict:
    if not context and 35 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
