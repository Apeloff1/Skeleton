"""Enemy max 0044.
"""
from __future__ import annotations

ID = "enemy_max_0044"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 44, "tier": 44 % 5}

def apply(context: str = "") -> dict:
    if not context and 44 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
