"""Quest advanced 0083.
"""
from __future__ import annotations

ID = "quest_adv_0083"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 83}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
