"""Enemy eco_apex 0273.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0273"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 273, "tier": 273 % 5}

def apply(context: str = "") -> dict:
    if not context and 273 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
