"""Quest advanced 0006.
"""
from __future__ import annotations

ID = "quest_adv_0006"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "index": 6}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
