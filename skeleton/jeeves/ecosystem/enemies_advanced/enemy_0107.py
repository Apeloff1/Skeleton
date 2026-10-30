"""Enemy advanced 0107.
"""
from __future__ import annotations

ID = "enemy_adv_0107"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 107}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
