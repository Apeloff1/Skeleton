"""Enemy advanced 0129.
"""
from __future__ import annotations

ID = "enemy_adv_0129"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 129}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
