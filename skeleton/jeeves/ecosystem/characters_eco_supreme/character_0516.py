"""Character eco_supreme 0516.
"""
from __future__ import annotations

ID = "character_eco_supreme_0516"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 516, "tier": 516 % 5}

def apply(context: str = "") -> dict:
    if not context and 516 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
