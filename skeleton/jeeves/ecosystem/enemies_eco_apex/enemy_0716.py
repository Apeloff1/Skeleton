"""Enemy eco_apex 0716.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0716"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 716, "tier": 716 % 5}

def apply(context: str = "") -> dict:
    if not context and 716 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
