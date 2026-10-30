"""Enemy advanced 0133.
"""
from __future__ import annotations

ID = "enemy_adv_0133"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 133}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
