"""Enemy ultra_max 0539.
"""
from __future__ import annotations

ID = "enemy_ultra_max_0539"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 539, "tier": 539 % 5}

def apply(context: str = "") -> dict:
    if not context and 539 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
