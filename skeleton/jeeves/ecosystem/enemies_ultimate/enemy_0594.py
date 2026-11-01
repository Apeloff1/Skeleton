"""Enemy ultimate 0594.
"""
from __future__ import annotations

ID = "enemy_ultimate_0594"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 594, "tier": 594 % 5}

def apply(context: str = "") -> dict:
    if not context and 594 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
