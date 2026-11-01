"""Enemy ultimate 0725.
"""
from __future__ import annotations

ID = "enemy_ultimate_0725"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 725, "tier": 725 % 5}

def apply(context: str = "") -> dict:
    if not context and 725 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
