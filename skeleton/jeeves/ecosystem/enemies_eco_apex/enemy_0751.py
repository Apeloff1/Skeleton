"""Enemy eco_apex 0751.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0751"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 751, "tier": 751 % 5}

def apply(context: str = "") -> dict:
    if not context and 751 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
