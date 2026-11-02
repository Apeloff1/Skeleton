"""Enemy eco_apex 0103.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0103"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 103, "tier": 103 % 5}

def apply(context: str = "") -> dict:
    if not context and 103 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
