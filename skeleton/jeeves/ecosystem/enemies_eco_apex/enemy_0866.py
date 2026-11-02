"""Enemy eco_apex 0866.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0866"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 866, "tier": 866 % 5}

def apply(context: str = "") -> dict:
    if not context and 866 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
