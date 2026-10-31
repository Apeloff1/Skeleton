"""Enemy max 0064.
"""
from __future__ import annotations

ID = "enemy_max_0064"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 64, "tier": 64 % 5}

def apply(context: str = "") -> dict:
    if not context and 64 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
