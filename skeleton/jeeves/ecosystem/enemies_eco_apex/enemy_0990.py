"""Enemy eco_apex 0990.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0990"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 990, "tier": 990 % 5}

def apply(context: str = "") -> dict:
    if not context and 990 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
