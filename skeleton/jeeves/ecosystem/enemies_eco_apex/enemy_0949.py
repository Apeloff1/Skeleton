"""Enemy eco_apex 0949.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0949"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 949, "tier": 949 % 5}

def apply(context: str = "") -> dict:
    if not context and 949 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
