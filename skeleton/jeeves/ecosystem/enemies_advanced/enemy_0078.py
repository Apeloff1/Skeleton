"""Enemy advanced 0078.
"""
from __future__ import annotations

ID = "enemy_adv_0078"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 78}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
