"""Enemy ultimate 0521.
"""
from __future__ import annotations

ID = "enemy_ultimate_0521"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 521, "tier": 521 % 5}

def apply(context: str = "") -> dict:
    if not context and 521 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
