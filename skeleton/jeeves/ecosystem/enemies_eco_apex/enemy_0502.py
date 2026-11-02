"""Enemy eco_apex 0502.
"""
from __future__ import annotations

ID = "enemy_eco_apex_0502"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 502, "tier": 502 % 5}

def apply(context: str = "") -> dict:
    if not context and 502 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
