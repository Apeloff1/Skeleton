"""Enemy eco_apex 0611.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0611"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 611, "tier": 611 % 5}

def apply(context: str = "") -> dict:
    if not context and 611 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
