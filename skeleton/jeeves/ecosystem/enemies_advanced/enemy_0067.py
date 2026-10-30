"""Enemy advanced 0067.
"""
from __future__ import annotations

ID = "enemy_adv_0067"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 67}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
