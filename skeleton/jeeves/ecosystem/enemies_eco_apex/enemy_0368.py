"""Enemy eco_apex 0368.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0368"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 368, "tier": 368 % 5}

def apply(context: str = "") -> dict:
    if not context and 368 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
