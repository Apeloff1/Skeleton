"""Enemy ultra_max 0276.
"""
from __future__ import annotations

ID = "enemy_ultra_max_0276"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 276, "tier": 276 % 5}

def apply(context: str = "") -> dict:
    if not context and 276 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
