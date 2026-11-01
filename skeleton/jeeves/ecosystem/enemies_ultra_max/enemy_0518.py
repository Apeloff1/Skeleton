"""Enemy ultra_max 0518.
"""
from __future__ import annotations

ID = "enemy_ultra_max_0518"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 518, "tier": 518 % 5}

def apply(context: str = "") -> dict:
    if not context and 518 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
