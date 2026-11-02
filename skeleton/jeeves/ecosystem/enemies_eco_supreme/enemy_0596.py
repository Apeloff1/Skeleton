"""Enemy eco_supreme 0596.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0596"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 596, "tier": 596 % 5}

def apply(context: str = "") -> dict:
    if not context and 596 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
