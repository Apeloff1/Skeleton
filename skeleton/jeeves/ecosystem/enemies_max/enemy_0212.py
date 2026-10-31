"""Enemy max 0212.
"""
from __future__ import annotations

ID = "enemy_max_0212"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 212, "tier": 212 % 5}

def apply(context: str = "") -> dict:
    if not context and 212 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
