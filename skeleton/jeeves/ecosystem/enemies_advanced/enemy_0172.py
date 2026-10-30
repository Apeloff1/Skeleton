"""Enemy advanced 0172.
"""
from __future__ import annotations

ID = "enemy_adv_0172"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 172}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
