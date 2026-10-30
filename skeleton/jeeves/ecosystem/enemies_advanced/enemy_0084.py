"""Enemy advanced 0084.
"""
from __future__ import annotations

ID = "enemy_adv_0084"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 84}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
