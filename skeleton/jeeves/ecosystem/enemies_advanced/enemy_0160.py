"""Enemy advanced 0160.
"""
from __future__ import annotations

ID = "enemy_adv_0160"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 160}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
