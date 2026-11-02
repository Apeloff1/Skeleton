"""Enemy eco_apex 0804.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0804"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 804, "tier": 804 % 5}

def apply(context: str = "") -> dict:
    if not context and 804 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
