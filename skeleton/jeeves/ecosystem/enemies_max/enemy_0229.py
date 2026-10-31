"""Enemy max 0229.
"""
from __future__ import annotations

ID = "enemy_max_0229"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 229, "tier": 229 % 5}

def apply(context: str = "") -> dict:
    if not context and 229 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
