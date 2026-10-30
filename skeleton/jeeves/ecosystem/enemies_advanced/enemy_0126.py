"""Enemy advanced 0126.
"""
from __future__ import annotations

ID = "enemy_adv_0126"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 126}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
