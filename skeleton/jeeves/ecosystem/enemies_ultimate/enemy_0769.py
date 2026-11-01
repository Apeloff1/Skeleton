"""Enemy ultimate 0769.
"""
from __future__ import annotations

ID = "enemy_ultimate_0769"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 769, "tier": 769 % 5}

def apply(context: str = "") -> dict:
    if not context and 769 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
