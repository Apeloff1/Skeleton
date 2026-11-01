"""Enemy supreme 0584.
"""
from __future__ import annotations

ID = "enemy_supreme_0584"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 584, "tier": 584 % 5}

def apply(context: str = "") -> dict:
    if not context and 584 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
