"""Enemy max 0286.
"""
from __future__ import annotations

ID = "enemy_max_0286"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 286, "tier": 286 % 5}

def apply(context: str = "") -> dict:
    if not context and 286 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
