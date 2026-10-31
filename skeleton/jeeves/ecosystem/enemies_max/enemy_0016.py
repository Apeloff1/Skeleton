"""Enemy max 0016.
"""
from __future__ import annotations

ID = "enemy_max_0016"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 16, "tier": 16 % 5}

def apply(context: str = "") -> dict:
    if not context and 16 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
