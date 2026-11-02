"""Enemy eco_supreme 0784.
"""
from __future__ import annotations

ID = "enemy_eco_supreme_0784"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 784, "tier": 784 % 5}

def apply(context: str = "") -> dict:
    if not context and 784 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
