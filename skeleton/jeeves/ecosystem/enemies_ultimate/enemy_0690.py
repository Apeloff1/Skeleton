"""Enemy ultimate 0690.
"""
from __future__ import annotations

ID = "enemy_ultimate_0690"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 690, "tier": 690 % 5}

def apply(context: str = "") -> dict:
    if not context and 690 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
