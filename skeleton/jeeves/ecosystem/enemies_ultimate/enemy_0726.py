"""Enemy ultimate 0726.
"""
from __future__ import annotations

ID = "enemy_ultimate_0726"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 726, "tier": 726 % 5}

def apply(context: str = "") -> dict:
    if not context and 726 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
