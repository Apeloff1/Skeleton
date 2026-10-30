"""Enemy advanced 0163.
"""
from __future__ import annotations

ID = "enemy_adv_0163"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 163}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
