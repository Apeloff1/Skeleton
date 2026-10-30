"""Enemy advanced 0143.
"""
from __future__ import annotations

ID = "enemy_adv_0143"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 143}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
