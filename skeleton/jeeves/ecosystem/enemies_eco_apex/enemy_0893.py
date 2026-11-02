"""Enemy eco_apex 0893.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0893"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 893, "tier": 893 % 5}

def apply(context: str = "") -> dict:
    if not context and 893 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
